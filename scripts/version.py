#!/usr/bin/env python3
"""Check and update the JS8Link version across all package files."""
# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026  JS8Link contributors

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

FILES = {
    "VERSION": ROOT / "VERSION",
    "backend/pyproject.toml": ROOT / "backend" / "pyproject.toml",
    "frontend/package.json": ROOT / "frontend" / "package.json",
}
SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


def read_version() -> str:
    return (ROOT / "VERSION").read_text().strip()


def write_version(version: str) -> None:
    (ROOT / "VERSION").write_text(version + "\n")


def check() -> bool:
    expected = read_version()
    ok = True
    if not SEMVER.fullmatch(expected):
        print(f"INVALID VERSION: {expected}")
        ok = False

    # Check pyproject.toml
    pyproject = (ROOT / "backend" / "pyproject.toml").read_text()
    for line in pyproject.splitlines():
        if line.strip().startswith("version ="):
            actual = line.split("=")[1].strip().strip('"')
            if actual != expected:
                print(f"MISMATCH backend/pyproject.toml: {actual} != {expected}")
                ok = False
            break

    # Check package.json
    with open(ROOT / "frontend" / "package.json") as f:
        pkg = json.load(f)
    if pkg.get("version") != expected:
        print(f"MISMATCH frontend/package.json: {pkg.get('version')} != {expected}")
        ok = False

    lock_text = (ROOT / "backend" / "uv.lock").read_text()
    lock_match = re.search(r'(?ms)^name = "js8link-backend"\nversion = "([^"]+)"', lock_text)
    if not lock_match or lock_match.group(1) != expected:
        actual = lock_match.group(1) if lock_match else "missing"
        print(f"MISMATCH backend/uv.lock: {actual} != {expected}")
        ok = False

    if ok:
        print(f"Version {expected} is synchronized")
    return ok


def set_version(version: str) -> None:
    if not SEMVER.fullmatch(version):
        raise ValueError(f"Version must be MAJOR.MINOR.PATCH: {version}")
    write_version(version)

    # Update pyproject.toml
    pyproject_path = ROOT / "backend" / "pyproject.toml"
    content = pyproject_path.read_text()
    updated = False
    lines = content.splitlines()
    for i, line in enumerate(lines):
        if line.strip().startswith("version ="):
            lines[i] = f'version = "{version}"'
            updated = True
            break
    if updated:
        pyproject_path.write_text("\n".join(lines) + "\n")

    # Update package.json
    pkg_path = ROOT / "frontend" / "package.json"
    with open(pkg_path) as f:
        pkg = json.load(f)
    pkg["version"] = version
    with open(pkg_path, "w") as f:
        json.dump(pkg, f, indent=2)
        f.write("\n")

    # Update package-lock.json version fields
    lock_path = ROOT / "frontend" / "package-lock.json"
    if lock_path.exists():
        with open(lock_path) as f:
            lock = json.load(f)
        lock["version"] = version
        if "packages" in lock and "" in lock["packages"]:
            lock["packages"][""]["version"] = version
        with open(lock_path, "w") as f:
            json.dump(lock, f, indent=2)
            f.write("\n")

    uv_lock_path = ROOT / "backend" / "uv.lock"
    if uv_lock_path.exists():
        content = uv_lock_path.read_text()
        updated = re.sub(
            r'(?ms)(^name = "js8link-backend"\nversion = )"[^"]+"',
            rf'\1"{version}"',
            content,
            count=1,
        )
        uv_lock_path.write_text(updated)

    print(f"Version set to {version}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: version.py <check|set VERSION>")
        sys.exit(1)
    command = sys.argv[1]
    if command == "check":
        sys.exit(0 if check() else 1)
    elif command == "set" and len(sys.argv) >= 3:
        set_version(sys.argv[2])
    else:
        print("Unknown command")
        sys.exit(1)
