import json
import re
from pathlib import Path
from typing import Dict

from transpilex.utils.logs import Log

BASE_DIR = Path(__file__).resolve().parent.parent
IMPORT_PATTERN_FILE = BASE_DIR / "patterns" / "import_patterns.json"
VARIABLE_PATTERN_FILE = BASE_DIR / "patterns" / "variable_patterns.json"


def _load_json(path: Path) -> Dict:
    if not path.exists():
        return {"patterns": {}}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {"patterns": {}}


def load_import_patterns() -> Dict[str, str]:
    """Load patterns."""
    patterns = _load_json(IMPORT_PATTERN_FILE).get("patterns", {})
    return {**patterns}


def load_variable_patterns() -> Dict[str, str]:
    """Load patterns."""
    patterns = _load_json(VARIABLE_PATTERN_FILE).get("patterns", {})
    return {**patterns}


def load_compiled_patterns() -> dict[str, re.Pattern]:
    """Load default patterns, compile them safely."""
    raw_patterns = load_import_patterns()
    compiled = {}
    for label, regex in raw_patterns.items():
        try:
            compiled[label] = re.compile(regex, re.MULTILINE | re.VERBOSE)
        except re.error as e:
            Log.warning(f"Invalid regex for '{label}': {e}")
    return compiled
