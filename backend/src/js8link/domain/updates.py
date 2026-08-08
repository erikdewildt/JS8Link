# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026  JS8Link contributors
import json
import re
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from packaging.version import InvalidVersion, Version

GITHUB_REPOSITORY_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
GITHUB_BRANCH_PATTERN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._/-]{0,126}[A-Za-z0-9])?$")


class UpdateError(RuntimeError):
    pass


@dataclass(frozen=True)
class GitHubBranch:
    repository: str
    branch: str
    commit: str
    message: str
    url: str


@dataclass(frozen=True)
class GitHubRelease:
    repository: str
    version: str
    tag: str
    prerelease: bool
    name: str
    body: str
    url: str
    assets: tuple[str, ...]


def normalize_github_repository(value: str) -> str:
    candidate = value.strip().removesuffix("/").removesuffix(".git")
    if "://" in candidate:
        parsed = urllib.parse.urlparse(candidate)
        if parsed.scheme != "https" or parsed.hostname not in {"github.com", "www.github.com"}:
            raise UpdateError("Only public HTTPS GitHub repositories are supported")
        candidate = parsed.path.strip("/")
    if not GITHUB_REPOSITORY_PATTERN.fullmatch(candidate):
        raise UpdateError("Use a GitHub repository in the form owner/repository")
    return candidate


def github_repository_from_remote_url(value: str) -> str:
    """Return owner/repository for a GitHub HTTPS or SSH remote URL."""
    candidate = value.strip()
    if candidate.startswith("git@github.com:"):
        candidate = candidate.removeprefix("git@github.com:")
    elif candidate.startswith("ssh://git@github.com/"):
        candidate = candidate.removeprefix("ssh://git@github.com/")
    return normalize_github_repository(candidate)


def origin_github_repository(root: Path) -> str:
    remote_url = git_output(root, "remote", "get-url", "origin")
    if not remote_url:
        raise UpdateError("This installation has no origin Git remote")
    try:
        return github_repository_from_remote_url(remote_url)
    except UpdateError as error:
        raise UpdateError("The origin Git remote is not a supported GitHub repository") from error


def validate_branch(value: str) -> str:
    branch = value.strip()
    if not GITHUB_BRANCH_PATTERN.fullmatch(branch) or ".." in branch or "//" in branch or branch.endswith(".lock"):
        raise UpdateError("Invalid GitHub branch name")
    return branch


def parse_version(value: str) -> Version:
    """Parse a release version using PEP 440's battle-tested comparator."""
    candidate = value.strip().removeprefix("v")
    try:
        return Version(candidate)
    except InvalidVersion as error:
        raise UpdateError(f"Invalid semantic version: {value}") from error


def _release_from_payload(repository: str, payload: dict[str, Any]) -> GitHubRelease | None:
    if payload.get("draft"):
        return None
    tag = str(payload.get("tag_name") or "")
    try:
        version = parse_version(tag)
    except UpdateError:
        return None
    assets = tuple(
        str(asset.get("name"))
        for asset in payload.get("assets", [])
        if isinstance(asset, dict) and asset.get("name")
    )
    return GitHubRelease(
        repository=repository,
        version=str(version),
        tag=tag,
        prerelease=bool(payload.get("prerelease")),
        name=str(payload.get("name") or tag),
        body=str(payload.get("body") or ""),
        url=str(payload.get("html_url") or f"https://github.com/{repository}/releases/tag/{tag}"),
        assets=assets,
    )


def get_github_releases(repository: str) -> list[GitHubRelease]:
    """Read public GitHub releases, retaining alpha/prerelease entries."""
    repository = normalize_github_repository(repository)
    request = urllib.request.Request(
        f"https://api.github.com/repos/{repository}/releases?per_page=100",
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "JS8Link-update-checker",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as error:
        raise UpdateError(f"GitHub returned HTTP {error.code}") from error
    except (OSError, urllib.error.URLError, ValueError) as error:
        raise UpdateError(f"Could not contact GitHub: {error}") from error
    if not isinstance(payload, list):
        raise UpdateError("GitHub returned an invalid releases response")
    releases = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        release = _release_from_payload(repository, item)
        if release is not None:
            releases.append(release)
    return sorted(releases, key=lambda release: parse_version(release.version), reverse=True)


def platform_artifact_names(*, system: str | None = None, machine: str | None = None) -> tuple[str, ...]:
    """Return the release asset names relevant to the current platform."""
    import platform

    system = (system or platform.system()).lower()
    machine = (machine or platform.machine()).lower()
    architecture = "arm64" if machine in {"arm64", "aarch64"} else "x86_64"
    if system == "windows":
        return ("JS8Link-windows-x86_64.zip",)
    if system == "darwin":
        return (f"JS8Link-macos-{architecture}.tar.gz", "JS8Link-macos-arm64.tar.gz", "JS8Link-macos-x86_64.tar.gz")
    return ("JS8Link-linux-x86_64.tar.gz",)


def get_github_branch(repository: str, branch: str) -> GitHubBranch:
    repository = normalize_github_repository(repository)
    branch = validate_branch(branch)
    encoded_branch = urllib.parse.quote(branch, safe="")
    request = urllib.request.Request(
        f"https://api.github.com/repos/{repository}/branches/{encoded_branch}",
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "JS8Link-update-checker",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            payload: dict[str, Any] = json.load(response)
    except urllib.error.HTTPError as error:
        if error.code == 404:
            raise UpdateError("GitHub repository or branch not found") from error
        raise UpdateError(f"GitHub returned HTTP {error.code}") from error
    except (OSError, urllib.error.URLError, ValueError) as error:
        raise UpdateError(f"Could not contact GitHub: {error}") from error

    commit = payload.get("commit") or {}
    commit_details = commit.get("commit") or {}
    message = str(commit_details.get("message") or "").splitlines()[0]
    sha = str(commit.get("sha") or "")
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise UpdateError("GitHub returned an invalid commit identifier")
    return GitHubBranch(
        repository=repository,
        branch=branch,
        commit=sha,
        message=message,
        url=str(commit.get("html_url") or f"https://github.com/{repository}/commit/{sha}"),
    )


def git_output(root: Path, *arguments: str) -> str | None:
    if not (root / ".git").exists():
        return None
    try:
        return subprocess.check_output(
            ["git", *arguments],
            cwd=root,
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=15,
        ).strip()
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None


def current_git_commit(root: Path) -> str | None:
    commit = git_output(root, "rev-parse", "HEAD")
    return commit if commit and re.fullmatch(r"[0-9a-f]{40}", commit) else None


def tracked_changes(root: Path) -> bool:
    status = git_output(root, "status", "--porcelain", "--untracked-files=no")
    return status is None or bool(status)
