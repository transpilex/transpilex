import os
import stat
import shutil


def force_remove_readonly(func, path, excinfo):
    os.chmod(path, stat.S_IWRITE)
    func(path)


def remove_git_folder(parent_path):
    git_folder = parent_path / ".git"
    if git_folder.exists() and git_folder.is_dir():
        shutil.rmtree(git_folder, onerror=force_remove_readonly)
