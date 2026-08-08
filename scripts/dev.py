#!/usr/bin/env python3
"""JS8Link development server — starts backend and frontend together."""
# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026  JS8Link contributors

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    backend_python = ROOT / "backend" / ".venv" / "bin" / "python"
    if not backend_python.exists():
        backend_python = Path(sys.executable)
    backend = subprocess.Popen(
        [
            str(backend_python),
            "-m",
            "uvicorn",
            "js8link.app:app",
            "--host",
            "0.0.0.0",
            "--port",
            "8009",
            "--reload",
        ],
        cwd=str(ROOT / "backend" / "src"),
    )
    frontend = subprocess.Popen(
        ["npm", "run", "dev"],
        cwd=str(ROOT / "frontend"),
    )
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        backend.terminate()
        frontend.terminate()
        backend.wait()
        frontend.wait()


if __name__ == "__main__":
    main()
