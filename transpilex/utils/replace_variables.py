import re
from pathlib import Path

from transpilex.utils.logs import Log


def replace_variables(folder_path: Path, variable_patterns: dict, replacement: str,
                      file_extension: str):
    """
    Scans a folder recursively for files matching given extensions,
    finds variables like '@@variable' or '{{ variable }}',
    and replaces them with a PHP echo statement.

    Args:
        folder_path (Path): Root folder to scan recursively.
        variable_patterns (dict): Regex patterns mapping labels to patterns.
        replacement (str): Replacement string for regex substitution.
        file_extension (str): File extension to process.

    Returns:
        int: Number of files modified.
    """
    folder = Path(folder_path).resolve()
    file_extension = file_extension if file_extension.startswith('.') else f'.{file_extension}'

    count = 0

    for file in folder.rglob(f"*{file_extension}"):
        if not file.is_file():
            continue

        try:
            content = file.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue

        original_content = content

        for regex in variable_patterns.values():
            try:
                content = re.sub(regex, replacement, content)
            except re.error:
                continue

        if content != original_content:
            file.write_text(content, encoding="utf-8")
            count += 1

    if count:
        Log.info(f"{count} files updated in {folder_path}")