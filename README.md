# JS8Link

JS8Link is a local station console for [JS8Call-improved](https://js8call.com/). It provides a
FastAPI backend and a Vite-built interface for monitoring the JS8 passband, inspecting stations,
chatting with stations, and operating the radio through JS8Call's TCP API.

The long-term goal is to provide a reliable communications layer and automatic multi-hop
communication over JS8. A simple station-to-station messaging workflow will be expanded in future
releases. JS8Link is also intended to support emergency communications (EMCOMM), where clear
status, dependable delivery workflows, and an auditable radio history are important.

> **Alpha status:** `0.0.2` is an early alpha. Test it carefully, keep database backups, and do
> not depend on it as the only channel for safety-critical communication.

JS8Link is an independent project and is not an official part of JS8Call.

## Features

- Live JS8 traffic, passband and station monitoring.
- Station locations, received SNR relationships, greyline/day-night display and history filters.
- Direct station conversations with per-chat speed and best-effort/confirmed delivery modes.
- Local SQLite storage with Alembic migrations and diagnostic traces.
- English and Dutch interface/help content, including dark and light operator-console themes.
- Standalone Windows, Linux and macOS packages; no Python or Node.js is required for end users.

## Requirements

End users need a supported Windows, Linux or macOS system and a working JS8Call-improved
installation. The release package contains its own Python runtime, FastAPI/Uvicorn application,
frontend assets and migration resources. Python, Node.js, npm, uv and Git are not required to run
the executable.

JS8Call itself must be installed and running separately.

## Download

Download alpha packages from the [JS8Link GitHub Releases](https://github.com/erikdewildt/JS8Link/releases)
page. Release archives are built from the exact commit represented by their tag and include
SHA-256 checksums.

## Installation

### Windows

1. Download `JS8Link-<version>-windows-x86_64.zip` from the releases page.
2. Extract it to a directory owned by your user.
3. Double-click `Start-JS8Link.bat` or start `JS8Link.exe` directly.
4. The default browser opens at `http://127.0.0.1:8008`.

The Windows archive is an application folder rather than an installer. It contains the executable
and all runtime resources, so Python and Node.js are not required. The batch launcher keeps the
working directory next to the executable and forwards optional arguments such as `--data-dir`.

Alpha binaries may trigger Windows SmartScreen because they are not code-signed yet. Verify the
download checksum and use the normal Windows option to allow a binary you trust; never disable
Windows security globally.

### Linux

```bash
tar -xzf JS8Link-<version>-linux-x86_64.tar.gz
cd JS8Link
./start-js8link.sh
```

The archive contains the executable, its bundled resources and `start-js8link.sh`. The launcher
is useful from a terminal and forwards command-line options. The Linux binary is built on a
current Ubuntu runner and may require a compatible glibc version on older distributions.

Do not use `sudo` for normal operation.

### macOS

Use `JS8Link-<version>-macos-arm64.dmg` on Apple Silicon or the `macos-x86_64` image on Intel.
Open the disk image and drag `JS8Link.app` to Applications, or run it directly from the mounted
image. The app bundle contains the FastAPI server, frontend and Python runtime; no Terminal,
Python or Node.js setup is needed.

The alpha builds are not signed or notarized yet. If Gatekeeper warns, use Control-click → Open or
the specific **Open Anyway** action in **System Settings → Privacy & Security**. Do not disable
Gatekeeper globally. The packaging workflow already creates a native `.app` and `.dmg`; signing
and notarization can be added later without changing the application runtime.

## Configure JS8Call

JS8Link communicates with JS8Call using TCP only:

```text
Protocol: TCP
Host:     127.0.0.1
Port:     2442

UDP is not used by JS8Link.
```

Configure JS8Call before starting JS8Link:

1. Install and start JS8Call-improved.
2. Confirm that the radio, audio and CAT configuration work in JS8Call.
3. Open JS8Call **Settings** and go to the **Reporting/API** settings.
4. Enable the JS8Call TCP API/TCP server.
5. Set the TCP port to `2442` and use `127.0.0.1` for local use.
6. Save the settings and leave JS8Call running.
7. Start JS8Link and confirm that its JS8Call status becomes **Connected**.

JS8Call may display UDP-related reporting options. They are not needed by JS8Link; JS8Link does
not use UDP fallback or automatically switch protocols.

See the official [JS8Call website](https://js8call.com/), [User Guide](https://js8call.com/JS8Call-improved/d6/d14/md_docs_2user__guide_2JS8Call__User__Guide.html),
[API documentation](https://js8call.com/JS8Call-improved/d7/d15/md_docs_2API.html), and
[JS8Call-improved source repository](https://github.com/JS8Call-improved/JS8Call-improved).

## Starting JS8Link

The packaged launcher starts the local FastAPI/Uvicorn server, runs required Alembic migrations,
waits for readiness, and opens the browser. It binds to `127.0.0.1:8008` by default.

```text
JS8Link
JS8Link --data-dir /path/to/data
JS8Link --port 8008
JS8Link --host 127.0.0.1
JS8Link --no-browser
```

The `--host` option is intentionally explicit. Do not bind to `0.0.0.0` unless exposing the
application on a network is an intentional, separately secured decision.

## Updating JS8Link

The application checks GitHub Releases, including alpha/prerelease versions, without blocking
normal local operation. It shows the current version, available version, release notes and the
platform artifact link. Version `0.0.2` does not replace its own executable automatically: close
JS8Link, download the new release, replace the application files, and start it again. Alembic
creates a database backup before a required schema migration.

## Application data

The database, logs and migration backups are kept outside the executable bundle. The default data
directory is supplied by `platformdirs`:

| Platform | Default directory |
| --- | --- |
| Windows | `%LOCALAPPDATA%\\JS8Link\\JS8Link` |
| Linux | `$XDG_DATA_HOME/JS8Link/JS8Link`, or `~/.local/share/JS8Link/JS8Link` |
| macOS | `~/Library/Application Support/JS8Link/JS8Link` |

Use `--data-dir <path>` to choose another location. The database is `<data-dir>/js8link.sqlite`;
logs are in `<data-dir>/logs`; migration backups are in `<data-dir>/backups`. Backups are not
deleted automatically in the alpha release.

Replacing or upgrading the executable does not remove the data directory. To restore a backup:

1. Stop JS8Link completely.
2. Make an extra copy of the current database.
3. Choose the desired backup from the documented backups directory.
4. Copy it to the database path as `js8link.sqlite`.
5. Start the JS8Link version compatible with that schema and verify the application.

If a migration is required, JS8Link makes a consistent SQLite backup first. If backup creation
fails, migration and startup are stopped. If migration fails, the backup is retained for manual
recovery.

## Troubleshooting

### JS8Link does not start

Check that the data directory is writable, that the bundled frontend exists, and that the launcher
is not already running. The terminal output and `<data-dir>/logs/js8link.log` contain the technical
cause.

### Port 8008 is already in use

Close the other process using port 8008 or choose an intentional alternative with `--port`. JS8Link
does not silently move to another port.

### JS8Call is not connected

Check that JS8Call is running, its TCP API/server is enabled, it listens on `127.0.0.1:2442`, and
the host/port in JS8Link match. A refused connection means no service is listening; a timeout can
indicate a firewall, wrong address, or an unresponsive service. JS8Link remains usable while
JS8Call is offline and retries according to its connection service.

### Update check failed

Internet access is optional. A DNS error, timeout, GitHub HTTP error, rate limit, malformed release
response or missing platform artifact is reported without stopping radio operation. Try again
later or open the [releases page](https://github.com/erikdewildt/JS8Link/releases) manually.

## Development

Development keeps the existing Vite hot-reload workflow. Requirements are Python 3.12+, uv,
Node.js/npm and just.

```bash
git checkout develop
git pull origin develop
just dev
```

The development Vite server uses port 8008 and proxies the backend on port 8009. It is separate
from the standalone launcher. Database schema changes use Alembic only:

```bash
just db-upgrade
just db-revision message="describe the schema change"
just db-current
just test
just check
```

Build a local package on the target operating system:

```bash
python3 scripts/build-executable.py
```

The script builds the frontend with `npm ci` and `npm run build`, then runs the explicit
`packaging/js8link.spec` PyInstaller configuration. On Windows and Linux the result is
`dist/JS8Link/` with the executable and resources. On macOS it additionally produces
`dist/JS8Link.app`. PyInstaller builds are native per target OS; they are not cross-platform
binaries.

The release workflow packages these outputs as a Windows ZIP, a Linux tarball and a macOS DMG.
Windows and Linux remain small onedir packages because the executable needs its bundled Python
extensions, frontend assets and migration resources next to it. This still behaves as a single
application for end users: there is no separate runtime installation or development server.

## Repository and release process

Source: [github.com/erikdewildt/JS8Link](https://github.com/erikdewildt/JS8Link). The canonical
development branch is `develop`; `main` contains released code. Protect `main` on GitHub with
required pull requests, blocked direct and force pushes, and blocked branch deletion.

Only a merged pull request from `develop` into `main` starts the release workflow. The workflow
reads `VERSION`, validates the matching tag `v<version>`, builds native Windows x86_64, Linux
x86_64 and macOS arm64 packages (and Intel macOS where available), runs smoke tests, creates
archives and `SHA256SUMS.txt`, then publishes `JS8Link <version> Alpha` as a GitHub prerelease.
Ordinary pushes to `develop` and merges from other branches do not publish releases.

The intended first-release flow is:

```bash
git checkout develop
git push origin develop
# Open and merge a pull request: develop -> main
```

The release commit, tag and all platform artifacts are the same source revision. No release is
started automatically by this working session.

## License

JS8Link is licensed under the [GNU General Public License v3.0](LICENSE), SPDX identifier
`GPL-3.0-only`. Third-party runtime notices are listed in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
