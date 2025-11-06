import json
from pathlib import Path
from transpilex.utils.logs import Log
from transpilex.config.project import ProjectConfig
from transpilex.config.base import GULP_DEV_DEPENDENCIES, VITE_DEV_DEPENDENCIES, GULP_TW_DEV_DEPENDENCIES, \
    VITE_TW_DEV_DEPENDENCIES


def update_package_json(
        config: ProjectConfig,
        deps: dict | None = None,
        dev_deps: dict | None = None,
        overrides: dict | None = None,
        ignore: list[str] | None = None
):
    """
    Deeply merges source and destination package.json files.

    Final behavior:
    - Start from destination package.json.
    - Merge in source fields, EXCEPT fields in `ignore`.
    - For ignored keys, keep destination's version as-is (do not overwrite with source).
    - Source still wins for meta fields (unless meta key is ignored).
    - For dependency-like keys (dependencies/devDependencies/peerDependencies/scripts):
      merge dictionaries (destination first, then source).
    - `deps`/`dev_deps` are appended if not already present.
    - `overrides` always wins in the end.

    Parameters:
        config (ProjectConfig)
        deps (dict | None): extra runtime deps to append
        dev_deps (dict | None): extra dev deps to append
        overrides (dict | None): hard overrides applied last
        ignore (list[str] | None): keys that should NOT be pulled from source
                                   (but existing dest values should remain)
    """

    source_path = config.src_path / "package.json"
    destination_path = config.project_root_path / "package.json"

    tailwind = config.ui_library == "tailwind"

    # pick default dev deps based on pipeline + ui_library
    if config.frontend_pipeline == "gulp":
        default_dev_deps = GULP_TW_DEV_DEPENDENCIES if tailwind else GULP_DEV_DEPENDENCIES
    elif config.frontend_pipeline == "vite":
        default_dev_deps = VITE_TW_DEV_DEPENDENCIES if tailwind else VITE_DEV_DEPENDENCIES
    else:
        default_dev_deps = {}

    if config.frontend_pipeline == "gulp":
        if tailwind:
            scripts = {
                "dev": "gulp",
                "build": "gulp build"
            }
        else:
            scripts = {
                "dev": "gulp",
                "build": "gulp build",
                "rtl": "gulp rtl",
                "rtl-build": "gulp rtlBuild"
            }
    else:
        scripts = {
            "dev": "vite",
            "build": "vite build"
        }

    deps = deps or {}
    dev_deps = dev_deps if dev_deps is not None else default_dev_deps
    overrides = overrides or {"scripts": scripts}
    ignore = set(ignore or [])

    def load_json(path: Path):
        if not path.exists():
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            Log.warning(f"Invalid or unreadable JSON at {path}")
            return {}

    def merge_field(dest_val, src_val, key):
        """
        Merge logic for a single top-level key.
        - If key is ignored: keep dest_val (do not use src_val at all).
        - For dependency-like keys that are dicts: deep merge.
        - Otherwise: source overrides destination.
        """
        if key in ignore:
            return dest_val

        dep_like_keys = {"dependencies", "devDependencies", "peerDependencies", "scripts"}

        if key in dep_like_keys and isinstance(dest_val, dict) and isinstance(src_val, dict):
            # destination first, then source (source can add/override individual packages/scripts)
            merged = {**dest_val, **src_val}
            return merged

        # default: source wins if provided, else dest
        return src_val if src_val is not None else dest_val

    source_data = load_json(source_path)
    dest_data = load_json(destination_path)

    # start with full destination snapshot
    data = dict(dest_data)

    # bring in every key from source using merge_field rules
    for key, src_val in source_data.items():
        dest_val = dest_data.get(key)
        data[key] = merge_field(dest_val, src_val, key)

    # Now apply meta priority (source wins) unless ignored
    meta_keys = ["name", "version", "description", "author", "license", "repository"]
    for key in meta_keys:
        if key in ignore:
            # if ignored, leave whatever is already in data (from dest or earlier merge)
            continue

        if key in source_data:
            data[key] = source_data[key]
        else:
            # fallbacks if both source and dest had nothing useful
            if key == "name":
                data.setdefault("name", config.project_name)
            elif key == "version":
                data.setdefault("version", "1.0.0")

    # Ensure dependency maps exist
    existing_deps = data.get("dependencies", {}) or {}
    existing_dev_deps = data.get("devDependencies", {}) or {}

    # build a set of all known packages to avoid duplicates
    all_existing = set(existing_deps.keys()) | set(existing_dev_deps.keys())

    # add runtime deps if not already declared anywhere
    for pkg, ver in deps.items():
        if pkg not in all_existing:
            existing_deps[pkg] = ver

    # add dev deps if not already declared anywhere
    for pkg, ver in dev_deps.items():
        if pkg not in all_existing:
            existing_dev_deps[pkg] = ver

    data["dependencies"] = existing_deps
    data["devDependencies"] = existing_dev_deps

    # apply hard overrides last
    for key, value in overrides.items():
        data[key] = value

    destination_path.parent.mkdir(parents=True, exist_ok=True)
    with open(destination_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    Log.info(f"package.json is ready at: {destination_path}")


def sync_package_json(
        config: ProjectConfig,
        deps: dict | None = None,
        dev_deps: dict | None = None,
        overrides: dict | None = None,
        ignore: list[str] | None = None
):
    """
    Deeply merges source and destination package.json files.

    Final behavior:
    - Start from destination package.json.
    - Merge in source fields, EXCEPT fields in `ignore`.
    - For ignored keys, keep destination's version as-is (do not overwrite with source).
    - Source still wins for meta fields (unless meta key is ignored).
    - For dependency-like keys (dependencies/devDependencies/peerDependencies/scripts):
      merge dictionaries (destination first, then source).
    - `deps`/`dev_deps` are appended if not already present.
    - `overrides` always wins in the end.

    Parameters:
        config (ProjectConfig)
        deps (dict | None): extra runtime deps to append
        dev_deps (dict | None): extra dev deps to append
        overrides (dict | None): hard overrides applied last
        ignore (list[str] | None): keys that should NOT be pulled from source
                                   (but existing dest values should remain)
    """

    source_path = config.src_path / "package.json"
    destination_path = config.project_root_path / "package.json"

    deps = deps or {}
    dev_deps = dev_deps or {}
    overrides = overrides or {}
    ignore = set(ignore or [])

    def load_json(path: Path):
        if not path.exists():
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            Log.warning(f"Invalid or unreadable JSON at {path}")
            return {}

    def merge_field(dest_val, src_val, key):
        """
        Merge logic for a single top-level key.
        - If key is ignored: keep dest_val (do not use src_val at all).
        - For dependency-like keys that are dicts: deep merge.
        - Otherwise: source overrides destination.
        """
        if key in ignore:
            return dest_val

        dep_like_keys = {"dependencies", "devDependencies", "peerDependencies", "scripts"}

        if key in dep_like_keys and isinstance(dest_val, dict) and isinstance(src_val, dict):
            # destination first, then source (source can add/override individual packages/scripts)
            merged = {**dest_val, **src_val}
            return merged

        # default: source wins if provided, else dest
        return src_val if src_val is not None else dest_val

    source_data = load_json(source_path)
    dest_data = load_json(destination_path)

    # start with full destination snapshot
    data = dict(dest_data)

    # bring in every key from source using merge_field rules
    for key, src_val in source_data.items():
        dest_val = dest_data.get(key)
        data[key] = merge_field(dest_val, src_val, key)

    # Now apply meta priority (source wins) unless ignored
    meta_keys = ["name", "version", "description", "author", "license", "repository"]
    for key in meta_keys:
        if key in ignore:
            # if ignored, leave whatever is already in data (from dest or earlier merge)
            continue

        if key in source_data:
            data[key] = source_data[key]
        else:
            # fallbacks if both source and dest had nothing useful
            if key == "name":
                data.setdefault("name", config.project_name)
            elif key == "version":
                data.setdefault("version", "1.0.0")

    # Ensure dependency maps exist
    existing_deps = data.get("dependencies", {}) or {}
    existing_dev_deps = data.get("devDependencies", {}) or {}

    # build a set of all known packages to avoid duplicates
    all_existing = set(existing_deps.keys()) | set(existing_dev_deps.keys())

    # add runtime deps if not already declared anywhere
    for pkg, ver in deps.items():
        if pkg not in all_existing:
            existing_deps[pkg] = ver

    # add dev deps if not already declared anywhere
    for pkg, ver in dev_deps.items():
        if pkg not in all_existing:
            existing_dev_deps[pkg] = ver

    data["dependencies"] = existing_deps
    data["devDependencies"] = existing_dev_deps

    # apply hard overrides last
    for key, value in overrides.items():
        data[key] = value

    destination_path.parent.mkdir(parents=True, exist_ok=True)
    with open(destination_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    Log.info(f"package.json is ready at: {destination_path}")
