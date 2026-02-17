#!/bin/bash
set -Eeuo pipefail

# Remove dist folder
# To avoid problems with uv publish
# that don't find the last version
rm -rf dist/
# Build the project
uv build
# Publish on Pypi
uv publish