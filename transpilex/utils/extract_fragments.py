from typing import Dict, List, Optional
import re


def extract_fragments(content: str, pattern: re.Pattern, type_label: str) -> List[Dict[str, Optional[str]]]:
    """
    Generic extractor for include-like syntax patterns across frameworks.
    Returns list of dicts: {'full': ..., 'path': ..., 'params': ..., 'type': type_label}
    """
    fragments = []
    for match in pattern.finditer(content):
        fragments.append({
            "full": match.group(0),
            "path": match.group("path").strip(),
            "params": match.group("params").strip() if match.group("params") else None,
            "type": type_label
        })
    return fragments
