import sys

from transpilex.config.base import LOG_COLORS


class Log:

    @staticmethod
    def _print(message: str, color: str = "", file=sys.stdout):
        print(f"{color}{message}{LOG_COLORS['RESET']}", file=file)

    @staticmethod
    def info(message: str):
        Log._print(message, LOG_COLORS["INFO"])

    @staticmethod
    def success(message: str):
        Log._print(message, LOG_COLORS["SUCCESS"])

    @staticmethod
    def warning(message: str):
        Log._print(message, LOG_COLORS["WARNING"])

    @staticmethod
    def error(message: str):
        Log._print(message, LOG_COLORS["ERROR"], file=sys.stderr)

    @staticmethod
    def created(path: str):
        Log._print(f"Created: {path}", LOG_COLORS["SUCCESS"])

    @staticmethod
    def updated(path: str):
        Log._print(f"Updated: {path}", LOG_COLORS["SUCCESS"])

    @staticmethod
    def removed(path: str):
        Log._print(f"Removed: {path}", LOG_COLORS["ERROR"])

    @staticmethod
    def preserved(path: str):
        Log._print(f"Preserved: {path}", LOG_COLORS["INFO"])

    @staticmethod
    def copied(path: str):
        Log._print(f"Copied: {path}", LOG_COLORS["SUCCESS"])

    @staticmethod
    def processed(path: str):
        Log._print(f"Processed: {path}", LOG_COLORS["SUCCESS"])

    @staticmethod
    def converted(path: str):
        Log._print(f"Converted: {path}", LOG_COLORS["SUCCESS"])

    @staticmethod
    def completed(task: str, location: str):
        Log._print(f"{task} completed at: {location}", LOG_COLORS["SUCCESS"])

    @staticmethod
    def project_start(project_name: str):
        Log._print(f"Initiating project setup for: {project_name}", LOG_COLORS["INFO"])

    @staticmethod
    def project_end(project_name: str, location: str):
        Log._print(f"Project setup completed for '{project_name}' at {location}",
                   LOG_COLORS["INFO"])
