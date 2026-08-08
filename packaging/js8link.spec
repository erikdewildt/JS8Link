import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules


ROOT = Path(SPECPATH).parent
BACKEND = ROOT / "backend"
FRONTEND_DIST = ROOT / "frontend" / "dist"

datas = [
    (str(FRONTEND_DIST), "frontend/dist"),
    (str(BACKEND / "alembic"), "alembic"),
    # Runtime-loaded JSON resources are not reliably discovered by
    # collect_data_files when the package is built from the source tree.
    (str(BACKEND / "src" / "js8link" / "data"), "js8link/data"),
    (str(BACKEND / "alembic.ini"), "."),
    (str(ROOT / "VERSION"), "."),
    (str(ROOT / "CHANGELOG.md"), "."),
    (str(ROOT / "LICENSE"), "."),
    (str(ROOT / "THIRD_PARTY_NOTICES.md"), "."),
]
datas += collect_data_files("js8link")

a = Analysis(
    [str(BACKEND / "src" / "js8link" / "runtime.py")],
    pathex=[str(BACKEND / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=collect_submodules("js8link")
    + ["aiosqlite", "uvicorn.logging", "uvicorn.loops.auto", "uvicorn.protocols.http.auto"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="JS8Link",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    exclude_binaries=True,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="JS8Link",
)

# On macOS, wrap the onedir contents in a native application bundle.  Windows
# and Linux intentionally keep the onedir layout: it is more transparent for
# troubleshooting and lets the launcher pass command-line options directly to
# the embedded executable.
if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="JS8Link.app",
        bundle_identifier="org.js8link.JS8Link",
    )
