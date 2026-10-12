#!/usr/bin/env python3
"""Check every dependency in a requirements.txt against PyPI.

Usage: python check_requirements.py [requirements.txt]

Uses the PyPI JSON API (https://docs.pypi.org/api/json/):
  https://pypi.org/pypi/<name>/json            -> 404 if the package does not exist
  https://pypi.org/pypi/<name>/<version>/json  -> 404 if the release does not exist
"""
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://pypi.org/pypi"

# name, optional [extras], optional version spec (operator + version)
LINE_RE = re.compile(
    r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*(?:\[[^\]]*\])?\s*(?:(==|===|~=|!=|<=|>=|<|>)\s*([^\s,;]+))?"
)


def fetch(url):
    """Return parsed JSON, or None on 404. Other errors raise."""
    req = urllib.request.Request(url, headers={"User-Agent": "requirements-checker/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def parse_line(line):
    """Return (name, pinned_version_or_None), or None if the line is not a package requirement."""
    line = line.split("#", 1)[0].strip()  # strip comments
    line = line.split(";", 1)[0].strip()  # strip environment markers
    if not line or line.startswith("-") or "://" in line or line.startswith((".", "/")):
        return None  # options, -r includes, URLs, local paths
    m = LINE_RE.match(line)
    if not m:
        return None
    name, op, version = m.groups()
    # Only an exact pin (== or ===) names a specific release to look up.
    pinned = version if op in ("==", "===") and "*" not in version else None
    return name, pinned


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "requirements.txt"
    if path == "-":  # read pasted lines from stdin (finish with Ctrl+Z on Windows / Ctrl+D on Mac/Linux)
        lines = sys.stdin.read().splitlines()
    else:
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
    entries = [p for p in (parse_line(l) for l in lines) if p]

    missing_packages = []
    missing_versions = []
    errors = []
    oldest = None  # (upload_time, "name==version")

    for name, version in entries:
        quoted = urllib.parse.quote(name)
        try:
            if fetch(f"{BASE}/{quoted}/json") is None:
                missing_packages.append(name)
                continue
            if version is None:
                continue  # package exists; nothing pinned to verify
            release = fetch(f"{BASE}/{quoted}/{urllib.parse.quote(version)}/json")
            if release is None:
                missing_versions.append(f"{name}=={version}")
                continue
            files = release.get("urls") or []
            if files and files[0].get("upload_time"):
                t = files[0]["upload_time"]  # first file listed under "urls"
                if oldest is None or t < oldest[0]:
                    oldest = (t, f"{name}=={version}")
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            errors.append(f"{name}: {e}")

    print(f"dependencies checked: {len(entries)}")
    print(f"packages not on pypi: {len(missing_packages)}")
    print(f"versions not on pypi: {len(missing_versions)}")
    if oldest:
        print(f"oldest pinned release : {oldest[1]}({oldest[0][:4]})")
    else:
        print("oldest pinned release : none")

    # Details, so you can see which lines were flagged
    if missing_packages:
        print("\nmissing packages: " + ", ".join(missing_packages))
    if missing_versions:
        print("missing versions: " + ", ".join(missing_versions))
    if errors:
        print("\nCould not check (network/API errors, not counted above):")
        for e in errors:
            print(f"  {e}")


if __name__ == "__main__":
    main()