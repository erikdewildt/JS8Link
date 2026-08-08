# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026  JS8Link contributors
import pytest

from js8link.domain.updates import (
    UpdateError,
    github_repository_from_remote_url,
    normalize_github_repository,
    parse_version,
    platform_artifact_names,
    validate_branch,
)


def test_semantic_versions_are_compared_numerically() -> None:
    assert parse_version("0.0.9") < parse_version("0.0.10")
    assert parse_version("0.9.9") < parse_version("0.10.0")


def test_platform_artifact_names_are_explicit() -> None:
    assert platform_artifact_names(system="Windows", machine="AMD64") == ("JS8Link-windows-x86_64.zip",)
    assert platform_artifact_names(system="Linux", machine="x86_64") == ("JS8Link-linux-x86_64.tar.gz",)
    assert platform_artifact_names(system="Darwin", machine="arm64")[0] == "JS8Link-macos-arm64.tar.gz"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("owner/repository", "owner/repository"),
        ("https://github.com/owner/repository", "owner/repository"),
        ("https://github.com/owner/repository.git", "owner/repository"),
    ],
)
def test_normalize_github_repository(value: str, expected: str) -> None:
    assert normalize_github_repository(value) == expected


@pytest.mark.parametrize("value", ["https://example.com/a/b", "owner", "owner/repo/extra", "git@github.com:a/b"])
def test_reject_unsupported_repository(value: str) -> None:
    with pytest.raises(UpdateError):
        normalize_github_repository(value)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("https://github.com/owner/repository.git", "owner/repository"),
        ("git@github.com:owner/repository.git", "owner/repository"),
        ("ssh://git@github.com/owner/repository.git", "owner/repository"),
    ],
)
def test_repository_from_git_remote(value: str, expected: str) -> None:
    assert github_repository_from_remote_url(value) == expected


@pytest.mark.parametrize("value", ["a", "main", "release/1.0", "feature_update"])
def test_validate_branch(value: str) -> None:
    assert validate_branch(value) == value


@pytest.mark.parametrize("value", ["../main", "feature//bad", "refs/heads/main.lock"])
def test_reject_unsafe_branch(value: str) -> None:
    with pytest.raises(UpdateError):
        validate_branch(value)
