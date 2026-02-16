import argparse
import traceback
from pathlib import Path

from transpilex.cli.prompts import ask_project_config, process_cli_config
from transpilex.config.project import ProjectConfig
from transpilex.frameworks.aiohttp import AIOHTTPConverter
from transpilex.frameworks.blazor import BlazorConverter
from transpilex.frameworks.cakephp import CakePHPConverter
from transpilex.frameworks.codeigniter import CodeIgniterConverter
from transpilex.frameworks.core import CoreConverter
from transpilex.frameworks.django import DjangoConverter
from transpilex.frameworks.fastapi import FastApiConverter
from transpilex.frameworks.flask import FlaskConverter
from transpilex.frameworks.laravel import LaravelConverter
from transpilex.frameworks.mvc import MVCConverter
from transpilex.frameworks.node import NodeConverter
from transpilex.frameworks.php import PHPConverter
from transpilex.frameworks.ror import RorConverter
from transpilex.frameworks.spring import SpringConverter
from transpilex.frameworks.symfony import SymfonyConverter
from transpilex.frameworks.yii import YiiConverter
from transpilex.utils.logs import Log
from transpilex.utils.pattern import load_compiled_patterns, load_variable_patterns


def parse_args():
    """Parses command-line arguments for non-interactive config."""
    parser = argparse.ArgumentParser(
        description="convert HTML projects to various web frameworks.",
        formatter_class=argparse.RawTextHelpFormatter
    )

    # Define the six requested arguments
    parser.add_argument(
        '-n', '--project-name',
        type=str,
        help='Name of the project. Must be lowercase letters only'
    )
    parser.add_argument(
        '-f', '--framework',
        type=str,
        help=f'Target framework'
    )
    parser.add_argument(
        '-u', '--ui-library',
        type=str,
        help=f'UI Library'
    )
    parser.add_argument(
        '-p', '--frontend-pipeline',
        type=str,
        help=f'Frontend pipeline'
    )
    parser.add_argument(
        '-s', '--src-path',
        type=str,
        help='Path to the source folder'
    )
    parser.add_argument(
        '-d', '--dest-path',
        type=str,
        help='Path to the destination folder'
    )

    return parser.parse_args()


def main():
    args = parse_args()
    cli_args = vars(args)

    core_cli_keys = ["project_name", "framework", "ui_library", "frontend_pipeline", "src_path", "dest_path"]
    is_cli_mode = any(cli_args.get(key) is not None for key in core_cli_keys)

    if is_cli_mode:
        try:
            project_config = process_cli_config(cli_args)
        except ValueError as e:
            Log.error(f"Configuration Error: {e}")
            return 1

    else:
        project_config = ask_project_config()
        if project_config is None:
            # Handles user cancellation
            return 1

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

    try:
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
        elif project_config["framework"] == "codeigniter":
            CodeIgniterConverter(config)
        elif project_config["framework"] == "node":
            NodeConverter(config)
        elif project_config["framework"] == "flask":
            FlaskConverter(config)
        elif project_config["framework"] == "symfony":
            SymfonyConverter(config)
        elif project_config["framework"] == "spring":
            SpringConverter(config)
        elif project_config["framework"] == "blazor":
            BlazorConverter(config)
        elif project_config["framework"] == "fastapi":
            FastApiConverter(config)
        elif project_config["framework"] == "yii":
            YiiConverter(config)
        elif project_config["framework"] == "aiohttp":
            AIOHTTPConverter(config)
        return 0
    except Exception as e:
        Log.error(f"Transpilation failed: {e}")
        traceback.print_exc()
        return 1
