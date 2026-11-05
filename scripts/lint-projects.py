#!/usr/bin/env python3
"""Lint the front matter of every project page under content/projects.

Checks (all errors, exit 1 on any):
  - front matter parses as a YAML mapping
  - required keys are present and non-empty (every taxonomy in hugo.yaml,
    plus title, repo and description)
  - no unknown keys (catches typos such as "descripton")
  - controlled vocabularies: maturity, ai_usage, involvement, types
  - descriptions are unique across projects (catches copy-pasted files)
  - repo looks like "owner/name"; logo and docs are https URLs
  - screenshot files exist in the page bundle and have descriptions
  - featured is a bool, ordinal an int, annotations a mapping of strings

With --github, also compares each description with the GitHub repo
description and reports differences (informational; needs `gh` and network).

Usage (from anywhere):
  python3 scripts/lint-projects.py [--github]
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.stderr.write("Error: PyYAML is required. Install with: pip install pyyaml\n")
    sys.exit(2)

REPO_ROOT = Path(__file__).resolve().parent.parent
PROJECTS_DIR = REPO_ROOT / "content" / "projects"
CONFIG_PATH = REPO_ROOT / "hugo.yaml"

ALLOWED_VALUES: dict[str, set[str]] = {
    "maturity": {"Production", "Beta", "Alpha", "Sandbox"},
    "ai_usage": {
        "Level 0: No AI",
        "Level 1: Assistant",
        "Level 2: Pair Programmer",
        "Level 3: Semi-Autonomous Engineer",
        "Level 4: Fully Autonomous Engineer",
    },
    "involvement": {"Founder", "Maintainer", "Contributor"},
    "types": {
        "Community",
        "Event Management",
        "Games",
        "Infrastructure & DevOps",
        "Libraries & Developer tools",
        "Personal Productivity",
        "Social",
        "Toys",
    },
}

EXTRA_REQUIRED = ("title", "repo", "description")
OPTIONAL_KEYS = {
    "annotations",
    "docs",
    "featured",
    "logo",
    "ordinal",
    "screenshots",
    "tags",
}

REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
FRONT_MATTER_RE = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)


def taxonomy_keys() -> list[str]:
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}
    return list((config.get("taxonomies") or {}).keys())


def project_files() -> list[Path]:
    flat = [p for p in PROJECTS_DIR.glob("*.md") if p.name != "_index.md"]
    bundles = list(PROJECTS_DIR.glob("*/index.md"))
    return sorted(flat + bundles)


def is_empty(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, (list, dict, str)):
        return len(value.strip() if isinstance(value, str) else value) == 0
    return False


def as_list(value: object) -> list[object]:
    return value if isinstance(value, list) else [value]


def normalise(text: str) -> str:
    return " ".join(text.split()).casefold().rstrip(".")


class Linter:
    def __init__(self, required: list[str]) -> None:
        self.required = required
        self.known_keys = set(required) | OPTIONAL_KEYS
        self.errors: list[str] = []

    def error(self, path: Path, message: str) -> None:
        self.errors.append(f"{path.relative_to(REPO_ROOT)}: {message}")

    def lint(self, path: Path) -> dict | None:
        match = FRONT_MATTER_RE.match(path.read_text(encoding="utf-8"))
        if not match:
            self.error(path, "missing or unterminated YAML front matter")
            return None
        try:
            fm = yaml.safe_load(match.group(1))
        except yaml.YAMLError as exc:
            self.error(path, f"invalid YAML: {exc}")
            return None
        if not isinstance(fm, dict):
            self.error(path, "front matter is not a mapping")
            return None

        for key in self.required:
            if is_empty(fm.get(key)):
                self.error(path, f"missing required key '{key}'")
        for key in sorted(set(fm) - self.known_keys):
            self.error(path, f"unknown key '{key}'")

        for key, allowed in ALLOWED_VALUES.items():
            for value in as_list(fm.get(key)):
                if value is not None and value not in allowed:
                    hint = next((a for a in allowed if a.casefold() == str(value).casefold()), None)
                    suffix = f" (did you mean '{hint}'?)" if hint else ""
                    self.error(path, f"{key}: '{value}' is not an allowed value{suffix}")

        self.check_types(path, fm)
        self.check_urls(path, fm)
        self.check_screenshots(path, fm)
        return fm

    def check_types(self, path: Path, fm: dict) -> None:
        if "featured" in fm and not isinstance(fm["featured"], bool):
            self.error(path, "featured must be true or false")
        if "ordinal" in fm and (isinstance(fm["ordinal"], bool) or not isinstance(fm["ordinal"], int)):
            self.error(path, "ordinal must be an integer")
        for key in ("technologies", "tags"):
            if key in fm and not isinstance(fm[key], list):
                self.error(path, f"{key} must be a list")
        annotations = fm.get("annotations")
        if annotations is not None:
            if not isinstance(annotations, dict):
                self.error(path, "annotations must be a mapping")
            else:
                for k, v in annotations.items():
                    if not isinstance(v, str):
                        self.error(path, f"annotations.{k} must be a quoted string, got {v!r}")
        description = fm.get("description")
        if isinstance(description, str) and description.strip() and not description.strip()[0].isupper():
            self.error(path, "description should start with a capital letter")

    def check_urls(self, path: Path, fm: dict) -> None:
        repo = fm.get("repo")
        if isinstance(repo, str) and not REPO_RE.match(repo):
            self.error(path, f"repo '{repo}' is not in 'owner/name' form")
        for key in ("logo", "docs"):
            value = fm.get(key)
            if value is not None and not (isinstance(value, str) and value.startswith("https://")):
                self.error(path, f"{key} must be an https:// URL")

    def check_screenshots(self, path: Path, fm: dict) -> None:
        screenshots = fm.get("screenshots")
        if screenshots is None:
            return
        if path.name != "index.md":
            self.error(path, "screenshots require a page bundle (dir/index.md)")
            return
        if not isinstance(screenshots, list):
            self.error(path, "screenshots must be a list")
            return
        for i, shot in enumerate(screenshots):
            if not isinstance(shot, dict) or not shot.get("file"):
                self.error(path, f"screenshots[{i}] needs a 'file'")
                continue
            if not (path.parent / shot["file"]).is_file():
                self.error(path, f"screenshots[{i}] file not found: {shot['file']}")
            if is_empty(shot.get("description")):
                self.error(path, f"screenshots[{i}] ({shot['file']}) needs a 'description' (used as alt text)")

    def check_duplicate_descriptions(self, pages: dict[Path, dict]) -> None:
        seen: dict[str, list[Path]] = defaultdict(list)
        for path, fm in pages.items():
            if isinstance(fm.get("description"), str):
                seen[normalise(fm["description"])].append(path)
        for paths in seen.values():
            if len(paths) > 1:
                names = ", ".join(str(p.relative_to(REPO_ROOT)) for p in paths)
                self.errors.append(f"duplicate description shared by: {names}")


def github_description(repo: str) -> str | None:
    result = subprocess.run(  # noqa: S603
        ["gh", "repo", "view", repo, "--json", "description"],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    return (json.loads(result.stdout).get("description") or "").strip()


def compare_with_github(pages: dict[Path, dict]) -> None:
    print("\nGitHub description comparison (informational):")
    for path, fm in pages.items():
        repo, local = fm.get("repo"), (fm.get("description") or "").strip()
        if not isinstance(repo, str):
            continue
        remote = github_description(repo)
        if remote is None:
            print(f"  {repo}: could not fetch")
        elif remote and normalise(remote) not in normalise(local):
            first_line = local.splitlines()[0] if local else "(none)"
            print(f"  {path.relative_to(REPO_ROOT)}\n    local:  {first_line}\n    github: {remote}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--github", action="store_true", help="compare descriptions with GitHub")
    args = parser.parse_args()

    linter = Linter(taxonomy_keys() + list(EXTRA_REQUIRED))
    pages: dict[Path, dict] = {}
    files = project_files()
    for path in files:
        fm = linter.lint(path)
        if fm is not None:
            pages[path] = fm
    linter.check_duplicate_descriptions(pages)

    if args.github:
        compare_with_github(pages)

    if linter.errors:
        print("\n".join(linter.errors))
        print(f"\n{len(linter.errors)} problem(s) in project front matter.")
        return 1
    print(f"OK: {len(files)} projects passed front-matter lint.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
