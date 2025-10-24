import os
import shutil
from pathlib import Path

from transpilex.config.base import FOLDERS, NO_NESTING_FOLDERS
from transpilex.utils.logs import Log

import os
import shutil
from pathlib import Path

from transpilex.config.base import FOLDERS, NO_NESTING_FOLDERS
from transpilex.utils.logs import Log


def _get_restructured_path(src_file: Path, src_root: Path, dest_root: Path) -> Path:
    """
    Calculates the new destination path for a file.
    - Parses filename left to right.
    - Folders are created only for consecutive FOLDER keywords at the start.
    - Stops nesting once a non-folder word appears.
    - Does NOT create a folder for the last token even if it's in FOLDERS.
    - Respects NO_NESTING_FOLDERS (flattens everything after those).
    """

    try:
        relative_path = src_file.relative_to(src_root)
    except ValueError:
        Log.warning(f"File {src_file} is not in {src_root}. Using filename only.")
        relative_path = Path(src_file.name)

    existing_parent = relative_path.parent
    filename = relative_path.name
    name_without_ext, ext = os.path.splitext(filename)

    parts = name_without_ext.split('-')

    folder_parts = []
    file_parts = []
    i = 0
    stop_at_no_nest = False
    nesting_stopped = False

    total_parts = len(parts)

    while i < total_parts:
        token = parts[i]

        # If already stopped nesting, remaining are file parts
        if nesting_stopped:
            file_parts.append(token)
            i += 1
            continue

        # Try matching folder tokens
        matched = False
        for fw in sorted(FOLDERS, key=lambda x: -len(x.split('-'))):
            fw_tokens = fw.split('-')
            token_range = parts[i:i + len(fw_tokens)]

            # Check folder match
            if token_range == fw_tokens:
                # If this is the last token(s) in filename -> treat as file part, not folder
                if i + len(fw_tokens) >= total_parts:
                    file_parts.extend(token_range)
                    i += len(fw_tokens)
                    matched = True
                    nesting_stopped = True
                    break

                folder_parts.append(fw)
                i += len(fw_tokens)
                matched = True

                # Stop nesting further if it's a NO_NESTING folder
                if fw in NO_NESTING_FOLDERS:
                    stop_at_no_nest = True
                break

        if not matched:
            # First non-folder token stops nesting
            nesting_stopped = True
            file_parts.append(token)
            i += 1

        if stop_at_no_nest:
            # Flatten all remaining tokens after no-nest folder
            remaining = parts[i:]
            file_parts.extend(remaining)
            break

    if not file_parts and folder_parts:
        file = folder_parts[-1] + ext
    elif file_parts:
        file = "-".join(file_parts) + ext
    else:
        file = filename

    if stop_at_no_nest:
        return Path(dest_root, folder_parts[0], file)

    return Path(dest_root, existing_parent, *folder_parts, file)


def restructure_and_copy_files(src_path: Path, dest_path: Path, extension: str = None):
    """
    Recursively copies all HTML files from src_path to dest_path,
    applying the restructuring logic to all files based on their parent folder.

    Args:
        src_path (Path): Source directory path.
        dest_path (Path): Destination directory path.
        extension (str, optional): New file extension (e.g., '.php').
                                  If not provided, keeps the original extension.
    """

    if not src_path.is_dir():
        Log.error(f"Source path is not a valid directory: {src_path}")
        return

    copied_count = 0

    for src_file in src_path.rglob("*.html"):
        if not src_file.is_file():
            continue

        # Get a destination path using restructure logic
        dest_file = _get_restructured_path(src_file, src_path, dest_path)

        if extension:
            dest_file = dest_file.with_suffix(extension if extension.startswith('.') else f".{extension}")

        try:
            dest_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_file, dest_file)
            copied_count += 1
        except Exception as e:
            Log.error(f"Failed to copy {src_file} to {dest_file}: {e}")

    Log.info(f"Restructured {copied_count} files to '{dest_path}'")
