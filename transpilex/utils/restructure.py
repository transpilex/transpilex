import os
import shutil
from pathlib import Path

from transpilex.config.base import FOLDERS, NO_NESTING_FOLDERS
from transpilex.config.project import ProjectConfig
from transpilex.utils.casing import apply_casing
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


def restructure_and_copy_files(config: ProjectConfig, dest_path: Path, extension: str = None,
                               case_style: str = "kebab"):
    """
    Recursively copies all HTML files from src_path to dest_path using your restructure logic,
    optionally changing file/folder naming convention to kebab-case or PascalCase,
    and returns a mapping of ORIGINAL html filenames -> NEW route path.

    Args:
        config: ProjectConfig object.
        dest_path (Path): Destination directory path.
        extension (str, optional): Extension for copied files.
        case_style (str, optional): Naming style for files and folders ("kebab" or "pascal").
                                   Defaults to "kebab".
    """

    def _apply_case_style(path: Path) -> Path:
        """
        Apply casing (kebab/pascal) to subfolders and filenames,
        but preserve the original casing of the project root path (e.g., core/Project).
        """
        root_parts = Path(config.project_root_path).parts if config else []
        root_len = len(root_parts)

        parts = []
        for i, part in enumerate(path.parts):
            # Preserve original root path casing (e.g. core/Project)
            # if i < root_len:
            #     # Use same exact casing from root_parts
            #     if i < len(root_parts):
            #         parts.append(root_parts[i])
            #     else:
            #         parts.append(part)
            #     continue

            # Split file name and extension
            stem, ext = (part, "") if "." not in part else part.rsplit(".", 1)

            # Apply case style
            if case_style == "pascal":
                new_stem = apply_casing(stem, "pascal")
            else:
                new_stem = apply_casing(stem, "kebab")

            parts.append(f"{new_stem}.{ext}" if ext else new_stem)

        return Path(*parts)

    if not config.pages_path.is_dir():
        Log.error(f"Source path is not a valid directory: {config.pages_path}")
        return {}

    copied_count = 0
    route_map: dict[str, str] = {}

    for src_file in config.pages_path.rglob("*.html"):
        if not src_file.is_file():
            continue

        # Apply restructure logic (as before)
        dest_file = _get_restructured_path(src_file, config.pages_path, dest_path)
        dest_file = _apply_case_style(dest_file)

        if extension:
            dest_file = dest_file.with_suffix(extension if extension.startswith('.') else f".{extension}")

        try:
            dest_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_file, dest_file)
            copied_count += 1

            # Route mapping
            # Always kebab-case in URLs, regardless of file/folder case
            try:
                rel_dest = dest_file.relative_to(dest_path)
            except ValueError:
                # Fallback for case mismatches (normalize case)
                rel_dest = Path(
                    str(dest_file).lower().replace(str(dest_path).lower(), "", 1).lstrip("/\\")
                )

            no_ext = rel_dest.with_suffix("")
            route_stem = apply_casing(no_ext.as_posix().removesuffix(".blade"), "kebab")
            route_path = "/" + route_stem.lstrip("/")

            route_map[src_file.name] = route_path

        except Exception as e:
            Log.error(f"Failed to copy {src_file} to {dest_file}: {e}")

    Log.info(f"Restructured {copied_count} files to '{dest_path}'")
    return route_map
