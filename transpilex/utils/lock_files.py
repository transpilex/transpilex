from pathlib import Path
from transpilex.utils.file import copy_items


def copy_lock_files(source_path: str | Path, dest_path: str | Path):
    files = ['package-lock.json', 'yarn.lock', 'bun.lock']

    for file in files:
        copy_items(Path(source_path / file), dest_path)
