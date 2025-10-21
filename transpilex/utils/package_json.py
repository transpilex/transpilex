import json
from pathlib import Path
from transpilex.utils.logs import Log
from transpilex.config.project import ProjectConfig
from transpilex.config.base import GULP_DEV_DEPENDENCIES, VITE_DEV_DEPENDENCIES


def update_package_json(
        config: ProjectConfig,
        deps: dict | None = None,
        dev_deps: dict | None = None,
        overrides: dict | None = None,
):
    """
    Deeply merges source and destination package.json files.
    Preserves all unique dependencies and prefers metadata from the source file.

    Priority Rules:
    - Source package.json wins for meta fields: name, version, description, author, license, repository.
    - Deep merge for: dependencies, devDependencies, peerDependencies, scripts.
    - Destination wins for all other fields.
    - Overrides parameter always takes highest priority.

    Parameters:
        config (ProjectConfig): Current project configuration.
        deps (dict | None): Additional dependencies to add (skipped if already exists).
        dev_deps (dict | None): Additional devDependencies to add or override.
        overrides (dict | None): Final explicit field overrides.
    """

    source_path = config.src_path / "package.json"
    destination_path = config.project_root_path / "package.json"

    default_dev_deps = {}
    if config.frontend_pipeline.lower() == "gulp":
        default_dev_deps = GULP_DEV_DEPENDENCIES
    elif config.frontend_pipeline.lower() == "vite":
        default_dev_deps = VITE_DEV_DEPENDENCIES

    deps = deps or {}
    dev_deps = dev_deps if dev_deps is not None else default_dev_deps
    overrides = overrides or {}

    def load_json(path: Path):
        if not path.exists():
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            Log.warning(f"Invalid or unreadable JSON at {path}")
            return {}

    def deep_merge(base: dict, update: dict,
                   merge_keys=("dependencies", "devDependencies", "peerDependencies", "scripts")):
        """Deep merge nested dependency objects, override other keys."""
        merged = dict(base)
        for key, val in update.items():
            if key in merge_keys and isinstance(val, dict):
                merged[key] = {**base.get(key, {}), **val}
            else:
                merged[key] = val
        return merged

    source_data = load_json(source_path)
    dest_data = load_json(destination_path)

    data = deep_merge(source_data, dest_data)

    meta_keys = ["name", "version", "description", "author", "license", "repository"]
    for key in meta_keys:
        if key in source_data:
            data[key] = source_data[key]
        else:
            # ensure fallback defaults
            if key == "name":
                data.setdefault("name", config.project_name)
            elif key == "version":
                data.setdefault("version", "1.0.0")

    existing_deps = data.get("dependencies", {})
    existing_dev_deps = data.get("devDependencies", {})

    all_existing = set(existing_deps.keys()) | set(existing_dev_deps.keys())

    for pkg, ver in deps.items():
        if pkg not in all_existing:
            existing_deps[pkg] = ver

    for pkg, ver in dev_deps.items():
        if pkg not in all_existing:
            existing_dev_deps[pkg] = ver

    data["dependencies"] = existing_deps
    data["devDependencies"] = existing_dev_deps

    for key, value in overrides.items():
        data[key] = value

    destination_path.parent.mkdir(parents=True, exist_ok=True)
    with open(destination_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    Log.info(f"package.json is ready at: {destination_path}")
