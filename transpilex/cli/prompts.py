import re
from pathlib import Path
import questionary
from questionary import Style

from transpilex.config.base import (
    SUPPORTED_FRAMEWORKS, VITE_ONLY, SUPPORTED_PIPELINES,
    SOURCE_PATH, ASSETS_PATH, DESTINATION_PATH,
    DEFAULT_PIPELINE, PARTIALS_PATH, UI_LIBRARIES, DEFAULT_UI_LIBRARY, PHP_VITE_ASSETS_PATH, PHP_ASSETS_PATH,
    PHP_VITE_PARTIALS_PATH, PHP_PARTIALS_PATH, PHP_VARIABLE_REPLACEMENT, PHP_EXTENSION, PAGES_PATH, LARAVEL_ASSETS_PATH,
    LARAVEL_PARTIALS_PATH, LARAVEL_VARIABLE_REPLACEMENT, LARAVEL_EXTENSION, GULP_PLUGINS_FOLDER, DJANGO_EXTENSION,
    DJANGO_ASSETS_PATH, DJANGO_PARTIALS_PATH, DJANGO_VARIABLE_REPLACEMENT, CORE_EXTENSION, CORE_ASSETS_PATH,
    CORE_PARTIALS_PATH, CORE_VARIABLE_REPLACEMENT, CORE_VITE_ASSETS_PATH, MVC_EXTENSION, MVC_ASSETS_PATH,
    MVC_VITE_ASSETS_PATH, MVC_PARTIALS_PATH, MVC_VARIABLE_REPLACEMENT, ROR_VITE_ASSETS_PATH, ROR_ASSETS_PATH,
    ROR_PARTIALS_PATH, ROR_VARIABLE_REPLACEMENT, ROR_EXTENSION, CAKEPHP_ASSETS_PATH, CAKEPHP_PARTIALS_PATH,
    CAKEPHP_VARIABLE_REPLACEMENT, CAKEPHP_EXTENSION, CODEIGNITER_ASSETS_PATH, CODEIGNITER_PARTIALS_PATH,
    CODEIGNITER_VARIABLE_REPLACEMENT, CODEIGNITER_EXTENSION, NODE_VARIABLE_REPLACEMENT, NODE_EXTENSION,
    NODE_PARTIALS_PATH, NODE_ASSETS_PATH, FLASK_ASSETS_PATH, FLASK_PARTIALS_PATH, FLASK_VARIABLE_REPLACEMENT,
    FLASK_EXTENSION, SYMFONY_ASSETS_PATH, SYMFONY_PARTIALS_PATH, SYMFONY_VARIABLE_REPLACEMENT,
    SYMFONY_EXTENSION, SPRING_ASSETS_PATH, SPRING_PARTIALS_PATH, SPRING_EXTENSION
)
from transpilex.config.project import GulpConfig
from transpilex.utils.file import folder_exists
from transpilex.utils.logs import Log
from transpilex.utils.pattern import load_compiled_patterns, load_variable_patterns

CUSTOM_QMARK = "›"

fresh_style = Style([
    ('qmark', 'fg:#56A8F5 bold'),
    ('question', 'bold'),
    ('selected', 'fg:#FFFFFF bg:#673AB7'),
    ('pointer', 'fg:#56A8F5 bold'),
    ('answer', 'fg:#6AAB73 bold'),
    ('error', 'fg:#F75464 bold'),
])


def is_valid_project_name(name: str):
    """Ensure project name is lowercase letters only."""
    if not name:
        return "Project name cannot be empty."
    if not re.match(r'^[a-z]+$', name.strip()):
        return "Only lowercase letters are allowed (no spaces, numbers, or symbols)."
    return True


def validate_folder_exists(path_str: str):
    """Ensure the given path exists and is a folder."""
    path = Path(path_str.strip() or ".")
    if not path.exists():
        return f"Path does not exist: {path}"
    if not path.is_dir():
        return f"Not a folder: {path}"
    return True


def safe_ask(prompt):
    """Helper: exit cleanly if the user cancels (Ctrl+C or Esc)."""
    if prompt is None:
        Log.error("\n Exiting...\n")
        exit(0)
    return prompt


def ask_project_config():
    project_name = safe_ask(questionary.text(
        "Project Name:",
        validate=is_valid_project_name,
        style=fresh_style,
        qmark=CUSTOM_QMARK
    ).ask())

    framework = safe_ask(questionary.select(
        "Select Framework:",
        choices=SUPPORTED_FRAMEWORKS,
        style=fresh_style,
        qmark=CUSTOM_QMARK,
    ).ask())

    ui_library = safe_ask(questionary.select(
        "Select UI Library:",
        choices=UI_LIBRARIES,
        style=fresh_style,
        qmark=CUSTOM_QMARK,
        default=DEFAULT_UI_LIBRARY,
    ).ask())

    if framework not in VITE_ONLY:
        frontend_pipeline = safe_ask(questionary.select(
            "Select Frontend Pipeline:",
            choices=SUPPORTED_PIPELINES,
            style=fresh_style,
            qmark=CUSTOM_QMARK,
            default=DEFAULT_PIPELINE
        ).ask())
    else:
        frontend_pipeline = 'Vite'

    src_path = safe_ask(questionary.path(
        "Source Folder Path:",
        default=SOURCE_PATH,
        style=fresh_style,
        qmark=CUSTOM_QMARK,
        validate=validate_folder_exists,
        only_directories=True
    ).ask())

    pages_path = safe_ask(questionary.path(
        "Source Pages Path:",
        default=PAGES_PATH,
        style=fresh_style,
        qmark=CUSTOM_QMARK,
        validate=validate_folder_exists,
        only_directories=True
    ).ask())

    asset_paths = safe_ask(questionary.path(
        "Source Assets Folder Path (Leave blank if assets are not in single folder. Use Advanced options to select multiple folders):",
        default=ASSETS_PATH,
        style=fresh_style,
        qmark=CUSTOM_QMARK,
        only_directories=True
    ).ask())

    partials_path = safe_ask(questionary.path(
        "Source Partials Folder Path (Leave blank if partials does not exist):",
        default=PARTIALS_PATH,
        style=fresh_style,
        qmark=CUSTOM_QMARK,
        only_directories=True
    ).ask())

    dest_path = safe_ask(questionary.path(
        "Destination Folder Path:",
        default=DESTINATION_PATH,
        style=fresh_style,
        qmark=CUSTOM_QMARK,
        validate=validate_folder_exists,
        only_directories=True
    ).ask())

    suffix = ""
    if ui_library.lower() == "tailwind" and frontend_pipeline.lower() == "vite":
        suffix = "-tw-vite"
    elif ui_library.lower() == "tailwind":
        suffix = "-tw"
    elif frontend_pipeline.lower() == "vite":
        suffix = "-vite"

    # Construct the parent folder name
    framework_folder = f"{framework.lower()}{suffix}"
    new_dest_path = Path(dest_path) / framework_folder

    if framework.lower() in ['core', 'mvc']:
        project_root_path = new_dest_path / project_name.title()
    else:
        project_root_path = new_dest_path / project_name

    if folder_exists(project_root_path):
        Log.error(f"Project already exists at: {project_root_path}")
        return None

    use_auth = questionary.confirm(
        "Include default authentication setup?",
        default=False,
        style=fresh_style,
        qmark=CUSTOM_QMARK,
    ).ask()

    framework = framework.lower()
    frontend_pipeline = frontend_pipeline.lower()
    plugins_folder = GULP_PLUGINS_FOLDER

    if framework == "php":
        if frontend_pipeline == "gulp":
            project_assets_path = PHP_ASSETS_PATH
            project_partials_path = PHP_PARTIALS_PATH
        else:
            project_assets_path = PHP_VITE_ASSETS_PATH
            project_partials_path = PHP_VITE_PARTIALS_PATH
        variable_replacement = PHP_VARIABLE_REPLACEMENT
        file_extension = PHP_EXTENSION

    elif framework == "laravel":
        project_assets_path = LARAVEL_ASSETS_PATH
        project_partials_path = LARAVEL_PARTIALS_PATH
        variable_replacement = LARAVEL_VARIABLE_REPLACEMENT
        file_extension = LARAVEL_EXTENSION

    elif framework == "django":
        project_assets_path = Path(project_name) / DJANGO_ASSETS_PATH
        project_partials_path = Path(project_name) / DJANGO_PARTIALS_PATH
        variable_replacement = DJANGO_VARIABLE_REPLACEMENT
        file_extension = DJANGO_EXTENSION

    elif framework == "core":
        if frontend_pipeline == "gulp":
            project_assets_path = CORE_ASSETS_PATH
        else:
            project_assets_path = CORE_VITE_ASSETS_PATH
        project_partials_path = CORE_PARTIALS_PATH
        variable_replacement = CORE_VARIABLE_REPLACEMENT
        file_extension = CORE_EXTENSION

    elif framework == "mvc":
        if frontend_pipeline == "gulp":
            project_assets_path = MVC_ASSETS_PATH
        else:
            project_assets_path = MVC_VITE_ASSETS_PATH
        project_partials_path = MVC_PARTIALS_PATH
        variable_replacement = MVC_VARIABLE_REPLACEMENT
        file_extension = MVC_EXTENSION

    elif framework == "ror":
        if frontend_pipeline == "gulp":
            project_assets_path = ROR_ASSETS_PATH
        else:
            project_assets_path = ROR_VITE_ASSETS_PATH
        project_partials_path = ROR_PARTIALS_PATH
        variable_replacement = ROR_VARIABLE_REPLACEMENT
        file_extension = ROR_EXTENSION

    elif framework == "cakephp":
        project_assets_path = CAKEPHP_ASSETS_PATH
        project_partials_path = CAKEPHP_PARTIALS_PATH
        variable_replacement = CAKEPHP_VARIABLE_REPLACEMENT
        file_extension = CAKEPHP_EXTENSION

    elif framework == "codeigniter":
        project_assets_path = CODEIGNITER_ASSETS_PATH
        project_partials_path = CODEIGNITER_PARTIALS_PATH
        variable_replacement = CODEIGNITER_VARIABLE_REPLACEMENT
        file_extension = CODEIGNITER_EXTENSION

    elif framework == "node":
        project_assets_path = NODE_ASSETS_PATH
        project_partials_path = NODE_PARTIALS_PATH
        variable_replacement = NODE_VARIABLE_REPLACEMENT
        file_extension = NODE_EXTENSION

    elif framework == "flask":
        project_assets_path = FLASK_ASSETS_PATH
        project_partials_path = FLASK_PARTIALS_PATH
        variable_replacement = FLASK_VARIABLE_REPLACEMENT
        file_extension = FLASK_EXTENSION

    elif framework == "symfony":
        project_assets_path = SYMFONY_ASSETS_PATH
        project_partials_path = SYMFONY_PARTIALS_PATH
        variable_replacement = SYMFONY_VARIABLE_REPLACEMENT
        file_extension = SYMFONY_EXTENSION

    elif framework == "spring":
        project_assets_path = SPRING_ASSETS_PATH
        project_partials_path = SPRING_PARTIALS_PATH
        variable_replacement = None
        file_extension = SPRING_EXTENSION

    else:
        project_assets_path = None
        project_partials_path = None
        variable_replacement = None
        file_extension = None

    # Advanced Options
    advanced = safe_ask(questionary.confirm(
        "Show advanced options?",
        default=False,
        style=fresh_style,
        qmark=CUSTOM_QMARK,
    ).ask())

    if advanced:
        choices = ["assets"]
        if frontend_pipeline == "gulp":
            choices.append("gulpfile")

        selected_options = safe_ask(questionary.checkbox(
            "Select one or more advanced options:",
            choices=choices,
            style=fresh_style,
            qmark=CUSTOM_QMARK
        ).ask())

        if "assets" in selected_options:

            questionary.print(
                "\nConfigure assets settings:",
                style="bold",
            )

            detect_assets = safe_ask(questionary.confirm(
                "Are your assets located in multiple folders?",
                default=False,
                style=fresh_style,
                qmark=CUSTOM_QMARK,
            ).ask())

            if detect_assets:
                assets = []
                questionary.print(
                    "\nAdd all folders that contain assets (CSS, JS, images, etc.). Leave blank when done.",
                    style="bold",
                )

                while True:
                    folder = safe_ask(questionary.path(
                        "Add folder:",
                        style=fresh_style,
                        qmark=CUSTOM_QMARK,
                        validate=validate_folder_exists,
                        only_directories=True
                    ).ask())
                    if not folder:
                        break
                    assets.append(Path(folder))

                if assets:
                    questionary.print(
                        f"{len(assets)} asset folders selected.",
                        style="fg:#6AAB73 bold",
                    )

                    project_assets_path = safe_ask(questionary.path(
                        "Destination folder path to merge all selected assets (relative to project root):",
                        style=fresh_style,
                        qmark=CUSTOM_QMARK,
                        default=str(project_assets_path)
                    ).ask())

                    asset_paths = assets

        if "gulpfile" in selected_options:
            questionary.print(
                "\nConfigure gulpfile settings:",
                style="bold",
            )

            plugins_folder = safe_ask(questionary.text(
                "Plugin Folder Name:",
                style=fresh_style,
                qmark=CUSTOM_QMARK,
                default=str(plugins_folder)
            ).ask())

    return {
        "project_name": project_name,
        "framework": framework,
        "ui_library": ui_library.lower(),
        "frontend_pipeline": frontend_pipeline,
        "src_path": Path(src_path).resolve(),
        "pages_path": Path(pages_path),
        "asset_paths": asset_paths if isinstance(asset_paths, (list, Path)) else (
            Path(asset_paths) if asset_paths else None),
        "partials_path": Path(partials_path) if len(partials_path) > 0 else None,
        "dest_path": Path(new_dest_path),
        "project_root_path": project_root_path,
        "project_assets_path": Path(project_root_path / project_assets_path),
        "project_partials_path": Path(project_root_path / project_partials_path),
        "use_auth": use_auth,
        "import_patterns": load_compiled_patterns(),
        "variable_patterns": load_variable_patterns(),
        "variable_replacement": variable_replacement,
        "file_extension": file_extension,
        "gulp_config": GulpConfig(
            src_path=project_assets_path,
            dest_path=project_assets_path,
            plugins_folder=plugins_folder
        )
    }


def process_cli_config(cli_args):
    required_keys = ['project_name', 'framework', 'ui_library', 'frontend_pipeline', 'src_path', 'dest_path']
    for key in required_keys:
        if not cli_args.get(key):
            raise ValueError(f"Missing required argument: --{key.replace('_', '-')}")

    project_name = cli_args['project_name']
    framework = cli_args['framework'].lower()
    ui_library = cli_args['ui_library'].lower()
    frontend_pipeline = cli_args['frontend_pipeline'].lower()

    src_path = Path(cli_args['src_path']).resolve()
    dest_path = Path(cli_args['dest_path'])

    if framework in VITE_ONLY and frontend_pipeline != 'vite':
        raise ValueError(f"Framework '{framework}' is Vite-only. Pipeline must be 'vite'.")
    elif framework not in VITE_ONLY and framework in SUPPORTED_FRAMEWORKS:
        if frontend_pipeline not in SUPPORTED_PIPELINES:
            raise ValueError(f"Pipeline '{frontend_pipeline}' is not valid for non-Vite-only frameworks.")

    suffix = ""
    if ui_library == "tailwind" and frontend_pipeline == "vite":
        suffix = "-tw-vite"
    elif ui_library == "tailwind":
        suffix = "-tw"
    elif frontend_pipeline == "vite":
        suffix = "-vite"

    framework_folder = f"{framework}{suffix}"
    new_dest_path = Path(dest_path) / framework_folder

    if framework in ['core', 'mvc']:
        project_root_path = new_dest_path / project_name.title()
    else:
        project_root_path = new_dest_path / project_name

    if folder_exists(project_root_path):
        raise ValueError(f"Project already exists at: {project_root_path}")

    pages_path = src_path / 'src'
    asset_paths = pages_path / 'assets'
    partials_path = pages_path / 'partials'

    use_auth = cli_args.get('use_auth', False)
    plugins_folder = cli_args.get('plugins_folder', GULP_PLUGINS_FOLDER)

    if framework == "php":
        if frontend_pipeline == "gulp":
            project_assets_path = PHP_ASSETS_PATH
            project_partials_path = PHP_PARTIALS_PATH
        else:
            project_assets_path = PHP_VITE_ASSETS_PATH
            project_partials_path = PHP_VITE_PARTIALS_PATH
        variable_replacement = PHP_VARIABLE_REPLACEMENT
        file_extension = PHP_EXTENSION

    elif framework == "laravel":
        project_assets_path = LARAVEL_ASSETS_PATH
        project_partials_path = LARAVEL_PARTIALS_PATH
        variable_replacement = LARAVEL_VARIABLE_REPLACEMENT
        file_extension = LARAVEL_EXTENSION

    elif framework == "django":
        project_assets_path = Path(project_name) / DJANGO_ASSETS_PATH
        project_partials_path = Path(project_name) / DJANGO_PARTIALS_PATH
        variable_replacement = DJANGO_VARIABLE_REPLACEMENT
        file_extension = DJANGO_EXTENSION

    elif framework == "core":
        if frontend_pipeline == "gulp":
            project_assets_path = CORE_ASSETS_PATH
        else:
            project_assets_path = CORE_VITE_ASSETS_PATH
        project_partials_path = CORE_PARTIALS_PATH
        variable_replacement = CORE_VARIABLE_REPLACEMENT
        file_extension = CORE_EXTENSION

    elif framework == "mvc":
        if frontend_pipeline == "gulp":
            project_assets_path = MVC_ASSETS_PATH
        else:
            project_assets_path = MVC_VITE_ASSETS_PATH
        project_partials_path = MVC_PARTIALS_PATH
        variable_replacement = MVC_VARIABLE_REPLACEMENT
        file_extension = MVC_EXTENSION

    elif framework == "ror":
        if frontend_pipeline == "gulp":
            project_assets_path = ROR_ASSETS_PATH
        else:
            project_assets_path = ROR_VITE_ASSETS_PATH
        project_partials_path = ROR_PARTIALS_PATH
        variable_replacement = ROR_VARIABLE_REPLACEMENT
        file_extension = ROR_EXTENSION

    elif framework == "cakephp":
        project_assets_path = CAKEPHP_ASSETS_PATH
        project_partials_path = CAKEPHP_PARTIALS_PATH
        variable_replacement = CAKEPHP_VARIABLE_REPLACEMENT
        file_extension = CAKEPHP_EXTENSION

    elif framework == "codeigniter":
        project_assets_path = CODEIGNITER_ASSETS_PATH
        project_partials_path = CODEIGNITER_PARTIALS_PATH
        variable_replacement = CODEIGNITER_VARIABLE_REPLACEMENT
        file_extension = CODEIGNITER_EXTENSION

    elif framework == "node":
        project_assets_path = NODE_ASSETS_PATH
        project_partials_path = NODE_PARTIALS_PATH
        variable_replacement = NODE_VARIABLE_REPLACEMENT
        file_extension = NODE_EXTENSION

    elif framework == "flask":
        project_assets_path = FLASK_ASSETS_PATH
        project_partials_path = FLASK_PARTIALS_PATH
        variable_replacement = FLASK_VARIABLE_REPLACEMENT
        file_extension = FLASK_EXTENSION

    elif framework == "symfony":
        project_assets_path = SYMFONY_ASSETS_PATH
        project_partials_path = SYMFONY_PARTIALS_PATH
        variable_replacement = SYMFONY_VARIABLE_REPLACEMENT
        file_extension = SYMFONY_EXTENSION

    elif framework == "spring":
        project_assets_path = SPRING_ASSETS_PATH
        project_partials_path = SPRING_PARTIALS_PATH
        variable_replacement = None
        file_extension = SPRING_EXTENSION

    else:
        project_assets_path = None
        project_partials_path = None
        variable_replacement = None
        file_extension = None

    return {
        "project_name": project_name,
        "framework": framework,
        "ui_library": ui_library,
        "frontend_pipeline": frontend_pipeline,
        "src_path": src_path,
        "pages_path": pages_path,
        "asset_paths": asset_paths,
        "partials_path": partials_path,
        "dest_path": new_dest_path,
        "project_root_path": project_root_path,
        "project_assets_path": Path(project_root_path / project_assets_path),
        "project_partials_path": Path(project_root_path / project_partials_path),
        "use_auth": use_auth,
        "import_patterns": load_compiled_patterns(),
        "variable_patterns": load_variable_patterns(),
        "variable_replacement": variable_replacement,
        "file_extension": file_extension,
        "gulp_config": GulpConfig(
            src_path=project_assets_path,
            dest_path=project_assets_path,
            plugins_folder=plugins_folder
        )
    }
