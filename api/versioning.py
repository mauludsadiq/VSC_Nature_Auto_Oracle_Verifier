from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass


API_VERSION = "v1"
BUNDLE_SCHEMA_VERSION = "v1"


def _run_git(args: list[str]) -> str:
    try:
        out = subprocess.check_output(["git"] + args, stderr=subprocess.DEVNULL)
        return out.decode("utf-8").strip()
    except Exception:
        return ""


def get_build_git_sha() -> str:
    sha = os.environ.get("BUILD_GIT_SHA", "").strip()
    if sha:
        return sha
    sha = _run_git(["rev-parse", "HEAD"])
    return sha or "UNKNOWN"


def get_repo_version() -> str:
    v = os.environ.get("REPO_VERSION", "").strip()
    if v:
        return v
    desc = _run_git(["describe", "--tags", "--always", "--dirty"])
    return desc or "0.0.0"


@dataclass(frozen=True)
class BuildMeta:
    api_version: str
    repo_version: str
    build_git_sha: str


def build_meta() -> BuildMeta:
    return BuildMeta(
        api_version=API_VERSION,
        repo_version=get_repo_version(),
        build_git_sha=get_build_git_sha(),
    )
