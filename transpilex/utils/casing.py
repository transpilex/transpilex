import re


def apply_casing(text: str, style: str):
    words = re.split(r'[\s_\-]+', text.strip())

    if style == "kebab":
        return "-".join(w.lower() for w in words)
    elif style == "snake":
        return "_".join(w.lower() for w in words)
    elif style == "pascal":
        return "".join(w.capitalize() for w in words)
    elif style == "camel":
        return words[0].lower() + "".join(w.capitalize() for w in words[1:])
    else:
        return text