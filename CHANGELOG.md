# Changelog

All notable user-facing changes to JS8Link are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and versions follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- Heartbeat responses transmitted by the local station no longer appear as chats with itself; they remain available in Band Monitor.

### Added

- Added platform-native release packaging: a macOS application/DMG, a Windows launcher and a
  Linux launcher alongside the standalone executable.
- Added the first standalone alpha distribution for Windows, Linux and macOS with bundled Python,
  frontend assets and Alembic migrations.
- Added persistent per-user data directories, startup diagnostics and safe database backups before
  required migrations.
- Added GitHub Releases metadata and manual update checks for alpha packages.

### Fixed

- Fixed release checksum generation for macOS application images.
- Fixed standalone release bundles so packaged frequency presets and other runtime data are included.
