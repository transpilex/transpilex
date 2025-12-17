import shutil
import re
from pathlib import Path
from typing import Union, List

from transpilex.config.base import PUBLIC_ONLY_ASSETS
from transpilex.utils.logs import Log


def copy_assets(
        asset_paths: Union[Path, List[Union[str, Path]]],
        destination_folder: Union[str, Path],
        preserve: List[str] | None = None,
        exclude: List[str] | None = None
):
    """
    Copy all assets from one or more source folders into a destination folder.
    """
    # Simply resolve the destination folder without forcing it into CWD
    destination_folder = Path(destination_folder).resolve()

    preserve = set(preserve or [])
    exclude = set(exclude or [])

    if isinstance(asset_paths, (str, Path)):
        asset_paths = [asset_paths]
    asset_paths = [Path(p).resolve() for p in asset_paths]

    if destination_folder.exists():
        for item in destination_folder.iterdir():
            if item.name in preserve:
                continue
            try:
                if item.is_dir():
                    shutil.rmtree(item)
                else:
                    item.unlink()
            except Exception as e:
                Log.warning(f"Failed to remove {item}: {e}")

    for src_path in asset_paths:
        if not src_path.exists():
            Log.warning(f"Source not found: {src_path}")
            continue

        dest_subfolder = destination_folder / src_path.name if len(asset_paths) > 1 else destination_folder
        dest_subfolder.mkdir(parents=True, exist_ok=True)

        for item in src_path.iterdir():
            if item.name in exclude:
                continue

            dest_item = dest_subfolder / item.name

            try:
                if item.is_dir():
                    shutil.copytree(item, dest_item, dirs_exist_ok=True)
                else:
                    shutil.copy2(item, dest_item)
            except Exception as e:
                Log.warning(f"Failed to copy {item}: {e}")

    Log.info(
        f"All assets copied to {destination_folder} (preserved: {', '.join(preserve) or 'none'}; excluded: {', '.join(exclude) or 'none'})")


def copy_public_only_assets(
        source_assets_path: Union[Path, List[Union[str, Path]]],
        destination_path: Path,
        candidates: List[str] | None = None
) -> List[str]:
    """
    Copies only selected public asset folders (like images, media, json, etc.)
    from one or more asset source paths into the destination folder.

    Args:
        source_assets_path (Path | list[str | Path]): One or more asset directories.
        destination_path (Path): Target directory for copied assets.
        candidates (list[str] | None): List of folder names to copy.
                                       Defaults to PUBLIC_ONLY_ASSETS.

    Returns:
        list[str]: Names of successfully copied folders (useful for exclude list in copy_assets).
    """

    if candidates is None:
        candidates = PUBLIC_ONLY_ASSETS

    destination_path = Path(destination_path).resolve()
    destination_path.mkdir(parents=True, exist_ok=True)

    copied = set()

    if isinstance(source_assets_path, (str, Path)):
        source_paths = [source_assets_path]
    else:
        source_paths = source_assets_path

    source_paths = [Path(p).resolve() for p in source_paths if Path(p).exists()]

    if not source_paths:
        Log.warning("No valid source asset folders found.")
        return []

    for src_path in source_paths:
        for name in candidates:
            src = src_path / name
            if src.exists() and src.is_dir():
                dest = destination_path / name
                try:
                    if dest.exists():
                        shutil.rmtree(dest)
                    shutil.copytree(src, dest)
                    copied.add(name)
                except Exception as e:
                    Log.warning(f"Failed to copy {src}: {e}")

    if copied:
        Log.copied(f"public assets: {', '.join(sorted(copied))}")

    return sorted(list(copied))


def clean_relative_asset_paths(content: str):
    """
    Cleans up <script src="...">, <link href="...">, and CSS url(...):
    - Removes leading 'assets/', '../assets/', etc.
    - Ensures cleaned local paths always start with '/'
    - Skips external URLs (with http://, https://, //, or domain names)
    """

    def clean_path(path: str) -> str:
        path = path.strip().strip('"\'')  # remove quotes if any

        # Skip if external (CDN, protocol, or domain)
        if re.match(r'^(?:[a-z]+:)?//|^[\w.-]+\.\w+/', path):
            return path

        # Remove relative asset prefixes
        cleaned = re.sub(r'^(\.{0,2}/)*assets/?', '', path)

        # Always prefix with '/'
        if not cleaned.startswith('/'):
            cleaned = '/' + cleaned

        return cleaned

    # Clean href/src attributes
    def attr_replacer(match):
        attr, path = match.groups()
        return f'{attr}="{clean_path(path)}"'

    content = re.sub(
        r'\b(src|href)\s*=\s*["\']([^"\']+)["\']',
        attr_replacer,
        content
    )

    # Clean CSS-style url(...)
    def css_url_replacer(match):
        path = match.group(1).strip(' "\'')
        cleaned = clean_path(path)
        return f'url({cleaned})'

    content = re.sub(
        r'url\(([^)]+)\)',
        css_url_replacer,
        content
    )

    return content


def replace_asset_paths(
        folders: Union[Path, list[Union[str, Path]]],
        new_base: str,
        extensions: list[str] | None = None,
):
    """
    Recursively scans all files in the given folder(s) for asset path patterns like
    ./assets/... , ../assets/... , /assets/... , or assets/... and replaces them with new_base.

    Args:
        folders (Path | list[str | Path]): Folder(s) to scan.
        new_base (str): Replacement base path (e.g. '~/assets/' or '/static/assets/').
        extensions (list[str], optional): File extensions to include (default: js, css, scss, html, cshtml).
    """

    # Default extensions if none provided
    if extensions is None:
        extensions = [".js", ".css", ".scss", ".ts", ".html", ".cshtml"]

    # Normalize folders into list of Path objects
    if isinstance(folders, Path):
        folders = [folders]
    elif isinstance(folders, list):
        folders = [Path(f) for f in folders]
    else:
        raise TypeError("folders must be a Path or list[str | Path]")

    # Regex pattern: match ./assets/, ../assets/, /assets/, or assets/
    asset_pattern = re.compile(
        r'(?<![A-Za-z0-9_])'  # not preceded by identifier chars
        r'(?:\.{0,2}/)*'  # optional ./ or ../ (any level)
        r'assets/',  # must contain 'assets/'
    )

    # Normalize new base path to have exactly one trailing slash
    new_base = new_base.rstrip("/") + "/"

    for folder in folders:
        if not folder.exists():
            Log.warning(f"Folder not found: {folder}")
            continue

        for file in folder.rglob("*"):
            if not file.is_file() or file.suffix.lower() not in extensions:
                continue

            try:
                content = file.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue

            # Perform replacement
            new_content = re.sub(asset_pattern, new_base, content)

            if new_content != content:
                file.write_text(new_content, encoding="utf-8")
