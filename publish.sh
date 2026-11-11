#!/usr/bin/env bash
#
# publish.sh — tag the current commit with the package version and publish to PyPI via uv.
#
# Usage:
#   PYPI_TOKEN=pypi-xxxx ./publish.sh
#
set -euo pipefail

# --- Helpers ---------------------------------------------------------------
die()  { echo "❌ $*" >&2; exit 1; }
info() { echo "▶ $*"; }

# --- Preconditions ---------------------------------------------------------
command -v uv  >/dev/null 2>&1 || die "uv is not installed or not on PATH."
command -v git >/dev/null 2>&1 || die "git is not installed or not on PATH."

[[ -n "${PYPI_TOKEN:-}" ]] || die "PYPI_TOKEN environment variable is not set."

# Run from the repository root
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || die "Not inside a git repository."
cd "$REPO_ROOT"

[[ -f pyproject.toml ]] || die "No pyproject.toml found at repo root ($REPO_ROOT)."

# --- Check for uncommitted changes -----------------------------------------
# --porcelain covers staged, unstaged, and untracked files.
if [[ -n "$(git status --porcelain)" ]]; then
  echo "Uncommitted changes detected:" >&2
  git status --short >&2
  die "Commit or stash your changes before publishing."
fi

# --- Determine version and tag ---------------------------------------------
VERSION="$(uv version --short 2>/dev/null || true)"
if [[ -z "$VERSION" ]]; then
  # Fallback for older uv versions without `uv version`
  VERSION="$(python3 -c 'import tomllib; print(tomllib.load(open("pyproject.toml","rb"))["project"]["version"])')" \
    || die "Could not read version from pyproject.toml."
fi
[[ -n "$VERSION" ]] || die "Version is empty."

TAG="v${VERSION}"
info "Preparing to publish version ${VERSION} (tag ${TAG})"

# Make sure the tag doesn't already exist locally or on the remote
if git rev-parse -q --verify "refs/tags/${TAG}" >/dev/null; then
  die "Tag ${TAG} already exists locally. Bump the version in pyproject.toml first."
fi
if git ls-remote --exit-code --tags origin "refs/tags/${TAG}" >/dev/null 2>&1; then
  die "Tag ${TAG} already exists on origin. Bump the version in pyproject.toml first."
fi

# --- Build (before tagging, so a failed build leaves no tag behind) --------
info "Cleaning dist/"
rm -rf dist/

info "Building package"
uv build

# --- Tag and push ----------------------------------------------------------
info "Creating tag ${TAG}"
git tag -a "${TAG}" -m "Release ${TAG}"

info "Pushing tag ${TAG} to origin"
if ! git push origin "${TAG}"; then
  git tag -d "${TAG}" >/dev/null
  die "Failed to push tag; local tag ${TAG} removed."
fi

# --- Publish ---------------------------------------------------------------
info "Publishing ${TAG} to PyPI"
uv publish --token "${PYPI_TOKEN}" dist/*

echo "✅ Published ${VERSION} to PyPI and pushed tag ${TAG}."
