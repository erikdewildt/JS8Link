#!/usr/bin/env python3
"""Build a standalone JS8Link executable using PyInstaller."""
# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026  JS8Link contributors

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    parser = argparse.ArgumentParser(description="Build JS8Link standalone executable")
    parser.add_argument("--skip-frontend-install", action="store_true", help="Reuse the existing node_modules directory")
    args = parser.parse_args()

    # Build frontend
    frontend_dir = ROOT / "frontend"
    npm = shutil.which("npm")
    if npm is None:
        raise SystemExit(
            "Cannot build JS8Link: npm was not found. Install Node.js 24+ for builds, "
            "or run with --skip-frontend-install after preparing frontend dependencies."
        )
    if not args.skip_frontend_install:
        subprocess.run([npm, "ci"], cwd=str(frontend_dir), check=True)
    subprocess.run([npm, "run", "build"], cwd=str(frontend_dir), check=True)

    # Ensure frontend build output exists at expected location
    # Build the explicit, reproducible onedir spec. The frontend is included
    # as read-only package data; writable data lives under platformdirs.
    subprocess.run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--clean",
            "--noconfirm",
            str(ROOT / "packaging" / "js8link.spec"),
        ],
        cwd=str(ROOT),
        check=True,
    )

    print("Build complete: dist/JS8Link/")


if __name__ == "__main__":
    main()
