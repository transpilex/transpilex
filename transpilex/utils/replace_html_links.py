import re


def replace_html_links(content: str, new_extension: str) -> str:
    def replace_match(match):
        original_url = match.group(1)

        if original_url.startswith(('http://', 'https://', '//', '/')):
            if original_url.endswith(".html"):
                temp_url_without_html = original_url.replace(".html", "")
                if new_extension == "":
                    return temp_url_without_html if not temp_url_without_html.endswith("/index") else "/"
                else:
                    return temp_url_without_html + new_extension
            else:
                return original_url

        if original_url.endswith(".html"):
            temp_url_without_html = original_url.replace(".html", "")

            if new_extension == "":
                processed_url_segment = temp_url_without_html if not temp_url_without_html.endswith("index") else ""
                final_url = "/" + processed_url_segment
                if final_url == "//":
                    final_url = "/"
                return final_url
            else:
                return temp_url_without_html + new_extension
        else:
            return original_url

    content = re.sub(r"""(?<=href=['"])([^'"]+)(?=['"])""", replace_match, content)
    content = re.sub(r"""(?<=action=['"])([^'"]+)(?=['"])""", replace_match, content)

    return content
