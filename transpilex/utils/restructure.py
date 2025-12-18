import os
import re
import shutil
from pathlib import Path

from transpilex.config.base import FOLDERS, NO_NESTING_FOLDERS
from transpilex.config.project import ProjectConfig
from transpilex.utils.casing import apply_casing
from transpilex.utils.logs import Log

def to_kebab_case(text: str) -> str:
    s1 = re.sub('(.)([A-Z][a-z]+)', r'\1-\2', text)
    s2 = re.sub('([a-z0-9])([A-Z])', r'\1-\2', s1)
    return re.sub(r'[-_]+', '-', s2).lower().strip('-')

def _get_restructured_path(src_file: Path, src_root: Path, dest_root: Path) -> Path:
    """
    Calculates the new destination path for a file.
    - Parses filename left to right.
    - Folders are created only for consecutive FOLDER keywords at the start.
    - Stops nesting once a non-folder word appears.
    - Does NOT create a folder for the last token even if it's in FOLDERS.
    - Respects NO_NESTING_FOLDERS (flattens everything after those).
    """

    src_root = Path(src_root).resolve()
    dest_root = Path(dest_root).resolve()
    src_file = Path(src_file).resolve()

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
        return (dest_root / folder_parts[0] / file).resolve()

    return (dest_root / existing_parent / Path(*folder_parts) / file).resolve()


def restructure_and_copy_files(config: ProjectConfig, dest_path: Path, extension: str = None,
                               case_style: str = "kebab"):
    """
    Restructures HTML files based on keywords and copies them to the destination.
    Generates a route_map that preserves hyphens by processing path segments individually.
    """
    dest_root = Path(dest_path).resolve()
    source_root = Path(config.pages_path).resolve()

    def _apply_case_style(absolute_dest_file: Path) -> Path:
        """Apply casing ONLY to the subfolders and filename, not the root path."""
        try:
            relative_part = absolute_dest_file.relative_to(dest_root)
            processed_parts = []

            for part in relative_part.parts:
                stem, ext = (part, "") if "." not in part else part.rsplit(".", 1)
                new_stem = apply_casing(stem, case_style or "kebab")
                processed_parts.append(f"{new_stem}.{ext}" if ext else new_stem)

            return dest_root / Path(*processed_parts)
        except ValueError:
            return absolute_dest_file

    if not source_root.is_dir():
        Log.error(f"Source path is not a valid directory: {source_root}")
        return {}

    copied_count = 0
    route_map: dict[str, str] = {}

    for src_file in source_root.rglob("*.html"):
        if not src_file.is_file():
            continue

        # Determine disk location using your existing logic
        dest_file = _get_restructured_path(src_file, source_root, dest_root)

        # Apply casing to the disk path
        dest_file = _apply_case_style(dest_file)

        # Add file extension
        if extension:
            ext_str = extension if extension.startswith('.') else f".{extension}"
            dest_file = dest_file.with_suffix(ext_str)

        try:
            dest_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_file, dest_file)
            copied_count += 1

            # Get relative path (e.g., Apps/IssueTracker.razor)
            rel_dest = dest_file.relative_to(dest_root)
            pure_path = rel_dest.parent / rel_dest.stem

            route_segments = []
            for part in pure_path.parts:
                # Use the robust kebab logic on each part individually
                clean_segment = to_kebab_case(part)
                route_segments.append(clean_segment)

            route_path = "/" + "/".join(route_segments)
            route_map[src_file.name] = route_path

        except Exception as e:
            Log.error(f"Failed to copy {src_file} to {dest_file}: {e}")

    Log.info(f"Restructured {copied_count} files to '{dest_root}'")
    return route_map
