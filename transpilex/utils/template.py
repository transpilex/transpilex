import shutil
from pathlib import Path
from transpilex.utils.logs import Log


def replace_file_with_template(template_file_path: Path, target_file_path: Path):
    """
    Replaces the content of a target file with the full content of a template file.

    Args:
        template_file_path: The path to the template file to read from.
        target_file_path: The path to the file that will be overwritten.
    """
    if not template_file_path.exists():
        Log.error(f"Template file not found: {template_file_path}")

    try:
        target_file_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(template_file_path, target_file_path)

    except OSError as e:
        Log.error(f"Failed to write file {target_file_path}: {e}")
    except Exception as e:
        Log.error(f"An unexpected error occurred: {e}")
