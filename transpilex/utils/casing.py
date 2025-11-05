import re


def apply_casing(s, case_type):
    if case_type == "kebab":
        s = re.sub(r'([a-z0-9])([A-Z])', r'\1-\2', s)
        return re.sub(r'[\s_]+', '-', s).lower()
    elif case_type == "pascal":
        parts = re.split(r'[-_\s]+', s)
        return ''.join(word.capitalize() for word in parts if word)
    return s
