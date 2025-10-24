import questionary
from questionary import Style
from pathlib import Path

from transpilex.cli.prompts import ask_basic_project_info, ask_advanced_options
from transpilex.config.project import ProjectConfig
from transpilex.frameworks.laravel import LaravelConverter
from transpilex.frameworks.php import PHPConvertor
from transpilex.utils.pattern import load_compiled_patterns, load_variable_patterns


def main():
    project_info = ask_basic_project_info()
    if project_info is None:
        return

    asset_paths, project_assets_path = ask_advanced_options(project_info["project_assets_path"])

    config = ProjectConfig(
        project_name=project_info["project_name"],
        framework=project_info["framework"],
        ui_library=project_info["ui_library"],
        frontend_pipeline=project_info["frontend_pipeline"],
        src_path=Path(project_info["src_path"]).resolve(),
        asset_paths=project_info["asset_paths"] if len(asset_paths) == 0 else asset_paths,
        partials_path=project_info["partials_path"],
        dest_path=project_info["dest_path"],
        pages_path=project_info["pages_path"],
        project_root_path=project_info["project_root_path"],
        project_assets_path=project_info["project_assets_path"],
        project_partials_path=project_info["project_partials_path"],
        use_auth=project_info["use_auth"],
        import_patterns=load_compiled_patterns(),
        variable_patterns=load_variable_patterns(),
        variable_replacement=project_info["variable_replacement"],
        file_extension=project_info["file_extension"],
        gulp_config=project_info["gulp_config"],
    )

    if project_info["framework"] == "php":
        PHPConvertor(config)
    elif project_info["framework"] == "laravel":
        LaravelConverter(config)
