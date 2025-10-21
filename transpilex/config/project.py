from dataclasses import dataclass
from pathlib import Path
import re


@dataclass
class GulpConfig:
    src_path: str
    dest_path: str
    plugins_folder: str


@dataclass
class ProjectConfig:
    project_name: str
    framework: str
    ui_library: str
    frontend_pipeline: str
    src_path: Path
    pages_path: Path
    asset_paths: Path | list[str | Path]
    partials_path: Path
    dest_path: Path
    project_root_path: Path
    project_partials_path: Path
    project_assets_path: Path
    use_auth: bool
    import_patterns: dict[str, re.Pattern]
    variable_patterns: dict[str, str]
    variable_replacement: str
    file_extension: str
    gulp_config: GulpConfig