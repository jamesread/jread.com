#!/usr/bin/env python3
"""
Download screenshot manifests published by project repos and sync their
screenshots into this site.

Each project in content/projects with a `repo:` front matter key is checked for
var/marketing/screenshots/screenshot-manifest.yaml on its default branch. When
a manifest exists:

  - a single-file project (foo.md) is converted to a page bundle (foo/index.md)
    so Hugo can treat the images as page resources;
  - every screenshot in the manifest is downloaded to foo/screenshots/<file>;
  - images in foo/screenshots/ that are no longer in the manifest are removed;
  - the `screenshots:` front matter list is replaced with the manifest entries.

Projects without a manifest are left untouched.

Usage (from repo root):
  python3 scripts/update-screenshots.py              # all projects
  python3 scripts/update-screenshots.py icehive      # only named projects
  python3 scripts/update-screenshots.py --dry-run
  python3 scripts/update-screenshots.py --force      # ignore the freshness check

Screenshots modified locally in the last 24 hours are not downloaded again,
unless --force is given.
"""

import argparse
import json
import os
import subprocess
import time
import sys
import urllib.error
import urllib.request
from pathlib import Path, PurePosixPath

try:
    import yaml
except ImportError:
    print("Error: PyYAML is required. Install with: pip install pyyaml", file=sys.stderr)
    sys.exit(1)

MANIFEST_PATH = "var/marketing/screenshots/screenshot-manifest.yaml"
RAW_BASE = "https://raw.githubusercontent.com"
SCREENSHOT_DIR = "screenshots"
IMAGE_SIGNATURES = {
    ".png": [b"\x89PNG\r\n\x1a\n"],
    ".jpg": [b"\xff\xd8\xff"],
    ".jpeg": [b"\xff\xd8\xff"],
    ".webp": [b"RIFF"],
    ".gif": [b"GIF87a", b"GIF89a"],
}
MAX_IMAGE_BYTES = 10 * 1024 * 1024
TIMEOUT = 30
FRESH_SECONDS = 24 * 60 * 60


def fetch(url: str) -> bytes | None:
    """Return the body at url, or None on 404."""
    req = urllib.request.Request(url, headers={"User-Agent": "jread.com-update-screenshots"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return resp.read(MAX_IMAGE_BYTES + 1)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def split_front_matter(content: str) -> tuple[list[str], str]:
    """Return (front matter lines without delimiters, body after closing ---)."""
    lines = content.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        raise ValueError("no front matter")
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return lines[1:i], "".join(lines[i + 1:])
    raise ValueError("unterminated front matter")


def find_projects(projects_dir: Path) -> list[Path]:
    """Return paths to each project's markdown file (foo.md or foo/index.md)."""
    pages = []
    for p in sorted(projects_dir.iterdir()):
        if p.is_file() and p.suffix == ".md" and not p.name.startswith("_"):
            pages.append(p)
        elif p.is_dir() and (p / "index.md").is_file():
            pages.append(p / "index.md")
    return pages


def project_name(page: Path) -> str:
    return page.parent.name if page.name == "index.md" else page.stem


def safe_filename(name: str) -> str:
    """Reject anything that is not a plain image filename."""
    pure = PurePosixPath(name)
    if pure.name != name or name.startswith(".") or "\\" in name:
        raise ValueError(f"unsafe screenshot filename: {name!r}")
    if pure.suffix.lower() not in IMAGE_SIGNATURES:
        raise ValueError(f"unsupported screenshot type: {name!r}")
    return name


def is_fresh(path: Path) -> bool:
    """True if path exists and was modified (mtime or ctime) within FRESH_SECONDS."""
    try:
        st = path.stat()
    except FileNotFoundError:
        return False
    return time.time() - max(st.st_mtime, st.st_ctime) < FRESH_SECONDS


def is_image(name: str, data: bytes) -> bool:
    return any(data.startswith(sig) for sig in IMAGE_SIGNATURES[PurePosixPath(name).suffix.lower()])


def yaml_str(value: str) -> str:
    # json.dumps produces a valid double-quoted YAML scalar.
    return json.dumps(value, ensure_ascii=False)


def render_screenshots_block(shots: list[dict]) -> list[str]:
    out = ["screenshots:\n"]
    for shot in shots:
        out.append(f"  - file: {yaml_str(SCREENSHOT_DIR + '/' + shot['file'])}\n")
        if shot.get("title"):
            out.append(f"    title: {yaml_str(shot['title'])}\n")
        if shot.get("description"):
            out.append(f"    description: {yaml_str(shot['description'])}\n")
    return out


def replace_screenshots_block(fm_lines: list[str], block: list[str]) -> list[str]:
    """Replace the top-level `screenshots:` key, or insert it before `annotations:` / at the end."""
    out = []
    insert_at = None
    i = 0
    while i < len(fm_lines):
        line = fm_lines[i]
        if line.startswith("screenshots:"):
            insert_at = len(out)
            i += 1
            # Skip the value: indented lines and blank lines up to the next top-level key.
            while i < len(fm_lines) and (fm_lines[i][:1] in (" ", "\t", "-") or not fm_lines[i].strip()):
                i += 1
            continue
        out.append(line)
        i += 1

    if insert_at is None:
        insert_at = next((n for n, l in enumerate(out) if l.startswith("annotations:")), len(out))
    return out[:insert_at] + block + out[insert_at:]


def git_tracked(path: Path) -> bool:
    return subprocess.run(
        ["git", "ls-files", "--error-unmatch", str(path)],
        capture_output=True,
    ).returncode == 0


def convert_to_bundle(page: Path, dry_run: bool) -> Path:
    bundle = page.with_suffix("")
    target = bundle / "index.md"
    print(f"  converting {page} -> {target}")
    if dry_run:
        return target
    bundle.mkdir(exist_ok=True)
    if git_tracked(page):
        subprocess.run(["git", "mv", str(page), str(target)], check=True)
    else:
        page.rename(target)
    return target


def load_manifest(repo: str) -> dict | None:
    url = f"{RAW_BASE}/{repo}/HEAD/{MANIFEST_PATH}"
    body = fetch(url)
    if body is None:
        return None
    manifest = yaml.safe_load(body)
    if not isinstance(manifest, dict) or manifest.get("version") != 1:
        raise ValueError(f"unsupported manifest at {url}")
    return manifest


def update_project(page: Path, dry_run: bool, force: bool) -> bool:
    content = page.read_text(encoding="utf-8")
    fm_lines, body = split_front_matter(content)
    fm = yaml.safe_load("".join(fm_lines)) or {}
    repo = fm.get("repo")
    if not repo:
        return False

    manifest = load_manifest(repo)
    if manifest is None:
        return False

    print(f"{project_name(page)}: found manifest in {repo}")
    shots = []
    for entry in manifest.get("screenshots") or []:
        name = safe_filename(str(entry["file"]))
        shots.append({**entry, "file": name})

    if page.name != "index.md":
        page = convert_to_bundle(page, dry_run)
    shot_dir = page.parent / SCREENSHOT_DIR

    wanted = {s["file"] for s in shots}
    for shot in shots:
        dest = shot_dir / shot["file"]
        if not force and is_fresh(dest):
            print(f"  skipping {dest} (modified in the last 24h)")
            continue
        url = shot.get("url") or f"{RAW_BASE}/{repo}/HEAD/var/marketing/screenshots/{shot['file']}"
        data = fetch(url)
        if data is None:
            raise ValueError(f"screenshot not found: {url}")
        if len(data) > MAX_IMAGE_BYTES or not is_image(shot["file"], data):
            raise ValueError(f"not a valid image (or too large): {url}")
        if dest.exists() and dest.read_bytes() == data:
            print(f"  unchanged {dest}")
            if not dry_run:
                os.utime(dest)  # mark as checked so the freshness window restarts
            continue
        print(f"  {'would write' if dry_run else 'writing'} {dest} ({len(data)} bytes)")
        if not dry_run:
            shot_dir.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)

    if shot_dir.is_dir():
        for stale in sorted(shot_dir.iterdir()):
            if stale.is_file() and stale.name not in wanted:
                print(f"  {'would remove' if dry_run else 'removing'} stale {stale}")
                if not dry_run:
                    stale.unlink()

    new_fm = replace_screenshots_block(fm_lines, render_screenshots_block(shots))
    new_content = "---\n" + "".join(new_fm) + "---\n" + body
    if new_content != content or not page.exists():
        print(f"  {'would update' if dry_run else 'updating'} {page}")
        if not dry_run:
            page.write_text(new_content, encoding="utf-8")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("projects", nargs="*", help="project names to update (default: all)")
    parser.add_argument("--dry-run", action="store_true", help="show what would change")
    parser.add_argument("--force", action="store_true", help="download screenshots even if modified in the last 24h")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    projects_dir = repo_root / "content" / "projects"
    pages = find_projects(projects_dir)
    if args.projects:
        pages = [p for p in pages if project_name(p) in args.projects]
        missing = set(args.projects) - {project_name(p) for p in pages}
        if missing:
            print(f"Error: unknown project(s): {', '.join(sorted(missing))}", file=sys.stderr)
            return 1

    failures = 0
    updated = 0
    for page in pages:
        try:
            if update_project(page, args.dry_run, args.force):
                updated += 1
        except Exception as e:  # keep going so one broken repo doesn't block the rest
            print(f"{project_name(page)}: ERROR {e}", file=sys.stderr)
            failures += 1

    print(f"{updated} project(s) with manifests, {failures} error(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
