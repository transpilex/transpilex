import shutil
from pathlib import Path
from typing import List, Union, Set, Optional

from transpilex.utils.logs import Log


def find_files_with_extension(
        folder: Union[str, Path],
        extension: str = '.html'
) -> List[Path]:
    """
    Recursively find all files in a folder (including subfolders)
    that match a single given extension.

    Args:
        folder (str | Path): The folder path to search in.
        extension (str): File extension to match (with or without dot), e.g. '.html' or 'html'.

    Returns:
        list[Path]: A list of full paths to matching files.
    """
    folder = Path(folder)
    extension = extension if extension.startswith('.') else f'.{extension}'
    extension = extension.lower()

    return [path for path in folder.rglob('*') if path.is_file() and path.suffix.lower() == extension]


def copy_and_change_extension(
        files: List[Path],
        source_folder: Union[str, Path],
        destination_folder: Union[str, Path],
        new_extension: str
) -> None:
    """
    Copy given files to a new folder, preserving their internal folder structure
    relative to the source folder, and change their extension to the given one.
    """
    source_folder = Path(source_folder).resolve()
    destination_folder = Path(destination_folder).resolve()
    new_extension = new_extension if new_extension.startswith('.') else f'.{new_extension}'

    for src_file in files:
        src_file = src_file.resolve()
        try:
            rel_path = src_file.relative_to(source_folder)
        except ValueError:
            rel_path = src_file.relative_to(source_folder.parent)

        new_name = rel_path.stem.replace('_', '-') + new_extension
        rel_path = rel_path.with_name(new_name)

        dest_file = destination_folder / rel_path
        dest_file.parent.mkdir(parents=True, exist_ok=True)

        shutil.copy2(src_file, dest_file)

    # Log.info(f"{len(files)} files processed and saved in {destination_folder.relative_to(Path.cwd())} with '{new_extension}' extension.")


def folder_exists(folder_path: Path) -> bool:
    """Return True if the folder exists and is a directory."""
    return folder_path.is_dir()


def file_exists(file_path: Path) -> bool:
    """Return True if the file exists and is a file."""
    return file_path.is_file()


def copy_items(
        source_paths: Union[str, Path, List[Union[str, Path]]],
        destination_path: Union[str, Path],
        clean_destination: bool = False,
        preserve: Optional[List[str]] = None,
        copy_mode: str = "self",  # NEW: "self" or "contents"
):
    """
    Copies one or more files or directories to a destination path.

    Args:
        source_paths: A single path (str or Path) or a list of paths to be copied.
        destination_path: Path (str or Path) to the destination. If copying a single
                          file, this can be a new filename. Otherwise, it must be a directory.
        clean_destination: If True, clears the destination directory before copying,
                           except for items in `preserve`. Applies only when destination is a directory.
        preserve: Filenames or directory names to keep in destination if cleaning.
        copy_mode: Defines folder copy behavior.
                   - "self" → copy the source folder itself into destination (default)
                   - "contents" → copy only the contents of the source folder
    """
    destination = Path(destination_path)
    if not isinstance(source_paths, list):
        source_paths = [source_paths]
    sources = [Path(p) for p in source_paths]

    # Determine if destination is a directory
    is_dest_dir = len(sources) > 1 or destination.is_dir()

    # Prepare destination directory
    if is_dest_dir:
        destination.mkdir(parents=True, exist_ok=True)
        if clean_destination:
            preserve_set: Set[str] = set(preserve or [])
            Log.info(
                f"Cleaning '{destination}'"
                f"{f' while preserving: {preserve_set}' if preserve_set else ''}"
            )
            for item in destination.iterdir():
                if item.name in preserve_set:
                    Log.preserved(item.name)
                    continue
                try:
                    if item.is_dir():
                        shutil.rmtree(item)
                        Log.removed(item.name)
                    else:
                        item.unlink()
                        Log.removed(item.name)
                except OSError as e:
                    Log.error(f"Error removing {item}: {e}")

    for source in sources:
        if not source.exists():
            Log.warning(f"Source not found and was skipped: {source}")
            continue

        target = destination / source.name if is_dest_dir else destination
        if not is_dest_dir:
            target.parent.mkdir(parents=True, exist_ok=True)

        try:
            if source.is_dir():
                if copy_mode == "contents":
                    # Copy contents of source folder, not the folder itself
                    for item in source.iterdir():
                        sub_target = destination / item.name if is_dest_dir else target / item.name
                        if item.is_dir():
                            shutil.copytree(item, sub_target, dirs_exist_ok=True)
                        else:
                            sub_target.parent.mkdir(parents=True, exist_ok=True)
                            shutil.copy2(item, sub_target)

                        # try:
                        #     src_rel = item.relative_to(Path.cwd())
                        # except ValueError:
                        #     src_rel = item.name
                        #
                        # Log.copied(f"{src_rel} → {target}")
                else:
                    # Default: copy the source folder itself
                    shutil.copytree(source, target, dirs_exist_ok=True)
                    # Log.copied(f"{source.name} -> {target}")
            elif source.is_file():
                shutil.copy2(source, target)
                # Log.copied(f"{source.name} -> {target}")
        except Exception as e:
            Log.error(f"Failed to copy {source.name} to {target}: {e}")


def move_files(source_folder: Path, destination_folder: Path, ignore_list: list[str] = None):
    """
    Moves all files from source_folder to destination_folder.
    Ignores files listed in ignore_list (if provided).
    """
    if ignore_list is None:
        ignore_list = []

    source_folder = Path(source_folder)

    if not source_folder.exists():
        return

    destination_folder = Path(destination_folder)
    destination_folder.mkdir(parents=True, exist_ok=True)

    for file_path in source_folder.glob("*"):
        if file_path.is_file() and file_path.name not in ignore_list:
            destination = destination_folder / file_path.name
            shutil.move(str(file_path), str(destination))

    try:
        if not any(source_folder.iterdir()):
            source_folder.rmdir()
    except FileNotFoundError:
        pass


def remove_item(path_to_remove: Path):
    """
    Removes a file or an entire directory (recursively).

    Args:
        path_to_remove: The Path object to the file or folder.
    """
    try:
        if not path_to_remove.exists():
            return

        if path_to_remove.is_dir():
            shutil.rmtree(path_to_remove)
        elif path_to_remove.is_file():
            path_to_remove.unlink()
        else:
            Log.warning(f"Path is not a file or directory: {path_to_remove}")

    except OSError as e:
        Log.error(f"Failed to remove {path_to_remove}: {e}")
    except Exception as e:
        Log.error(f"An unexpected error occurred while removing {path_to_remove}: {e}")


def empty_folder_contents(folder_path: Path, skip=None):
    """
    Deletes all contents inside the given folder (files and subfolders),
    but keeps the folder itself.

    :param folder_path: The folder to empty.
    :param skip: Optional list of file or directory names to skip from deletion.
    """
    folder_path = Path(folder_path)
    skip = set(skip or [])

    if not folder_path.exists() or not folder_path.is_dir():
        return

    for item in folder_path.iterdir():
        if item.name in skip:
            continue
        try:
            if item.is_file() or item.is_symlink():
                item.unlink()
            elif item.is_dir():
                shutil.rmtree(item)
        except Exception as e:
            Log.error(f"Error removing {item}: {e}")

    if not any(folder_path.iterdir()):
        folder_path.rmdir()


def rename_item(
        source: Union[str, Path],
        new_name: str,
        overwrite: bool = False
) -> Optional[Path]:
    """
    Renames a file or directory safely.

    Args:
        source: Path to the file or directory to rename.
        new_name: The new name (not full path — just the filename or directory name).
        overwrite: If True, overwrites an existing file or directory with the same name.

    Returns:
        Path to the renamed item, or None if operation failed.
    """
    source_path = Path(source)
    if not source_path.exists():
        Log.error(f"Cannot rename: '{source_path}' does not exist.")
        return None

    # Build target path (in same parent directory)
    target_path = source_path.parent / new_name

    # Prevent overwriting unless explicitly allowed
    if target_path.exists():
        if not overwrite:
            Log.warning(f"Target '{target_path}' already exists.")
            return None
        else:
            # Remove the existing destination before renaming
            try:
                if target_path.is_dir():
                    shutil.rmtree(target_path)
                else:
                    target_path.unlink()
                Log.removed(f"Existing '{target_path}' removed for overwrite.")
            except Exception as e:
                Log.error(f"Failed to remove existing '{target_path}': {e}")
                return None

    try:
        source_path.rename(target_path)
        return target_path
    except Exception as e:
        Log.error(f"Failed to rename '{source_path}' to '{new_name}': {e}")
        return None
