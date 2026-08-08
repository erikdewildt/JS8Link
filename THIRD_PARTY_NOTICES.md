# Third-party notices

JS8Link is distributed under the GNU General Public License v3.0, SPDX `GPL-3.0-only`. The
following runtime dependencies are bundled or shipped with the application under their own
licenses. Their license terms remain applicable and are not replaced by the JS8Link project
license.

## Python runtime dependencies

FastAPI, Starlette, Pydantic, Pydantic Settings, Uvicorn, SQLAlchemy, Alembic, aiosqlite,
platformdirs and argon2-cffi are distributed under the licenses declared by their upstream
packages. The exact locked versions and package metadata are recorded in `backend/uv.lock`.
PyInstaller is a build-time dependency and is not part of the application source runtime.

## Frontend dependencies

React, React DOM, Vite, TypeScript, MapLibre GL, Tabler Icons, Lucide, Fontsource IBM Plex fonts,
and the remaining npm packages are distributed under the licenses declared in
`frontend/package-lock.json`. The lockfile is the authoritative list for the release build.

Before publishing a release, review the generated dependency metadata for any package whose license
or additional attribution requirements are unclear. Keep any upstream notices required by those
licenses in the release archive.
