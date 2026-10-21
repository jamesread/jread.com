#!/usr/bin/env python3
"""
Check that every project in content/projects has all taxonomy labels defined
in hugo.yaml. Reports any project missing one or more taxonomies.

Usage (from repo root):
  python3 scripts/check-project-taxonomies.py
  # or
  ./scripts/check-project-taxonomies.py
"""

import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("Error: PyYAML is required. Install with: pip install pyyaml", file=sys.stderr)
    sys.exit(1)


def load_yaml(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_taxonomy_keys(config_path: Path) -> list[str]:
    config = load_yaml(config_path)
    taxonomies = config.get("taxonomies") or {}
    return list(taxonomies.keys())


def extract_front_matter(content: str) -> tuple[dict | None, str]:
    """Extract YAML front matter from markdown content. Returns (parsed_dict, rest)."""
    if not content.startswith("---"):
        return None, content
    parts = content.split("---", 2)
    if len(parts) < 3:
        return None, content
    try:
        fm = yaml.safe_load(parts[1])
        return (fm if isinstance(fm, dict) else None), parts[2]
    except yaml.YAMLError:
        return None, content


def is_empty_value(value) -> bool:
    """Treat missing, None, empty list, or empty string as empty."""
    if value is None:
        return True
    if isinstance(value, list):
        return len(value) == 0
    if isinstance(value, str):
        return value.strip() == ""
    return False


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    config_path = repo_root / "hugo.yaml"
    projects_dir = repo_root / "content" / "projects"

    if not config_path.exists():
        print(f"Error: Config not found: {config_path}", file=sys.stderr)
        return 1
    if not projects_dir.is_dir():
        print(f"Error: Projects dir not found: {projects_dir}", file=sys.stderr)
        return 1

    taxonomy_keys = get_taxonomy_keys(config_path)
    if not taxonomy_keys:
        print("No taxonomies defined in hugo.yaml.", file=sys.stderr)
        return 0

    project_files = sorted(f for f in projects_dir.glob("*.md") if f.name != "_index.md")
    if not project_files:
        print("No project files found.", file=sys.stderr)
        return 0

    missing: dict[str, list[str]] = {}  # project -> list of missing taxonomy keys

    for path in project_files:
        content = path.read_text(encoding="utf-8")
        fm, _ = extract_front_matter(content)
        if fm is None:
            missing[path.name] = list(taxonomy_keys)
            continue
        project_missing = []
        for key in taxonomy_keys:
            value = fm.get(key)
            if is_empty_value(value):
                project_missing.append(key)
        if project_missing:
            missing[path.name] = project_missing

    if not missing:
        print(f"OK: All {len(project_files)} projects have every taxonomy ({', '.join(taxonomy_keys)}).")
        return 0

    print(f"Taxonomies defined: {', '.join(taxonomy_keys)}\n")
    print("Projects missing one or more taxonomies:\n")
    for name in sorted(missing.keys()):
        keys = missing[name]
        print(f"  {name}")
        print(f"    missing: {', '.join(keys)}")
    print(f"\nTotal: {len(missing)} project(s) with missing taxonomies.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
