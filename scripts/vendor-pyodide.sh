#!/usr/bin/env bash
# Vendor the pyodide "full" bundle for offline demo fallback.
# Populates data/pyodide-dist/ so widgets.jsx's Notebook can boot pyodide
# without the network (the CDN is the primary path — see pickIndexURL()).
# Run once: bash scripts/vendor-pyodide.sh
set -euo pipefail

VERSION="314.0.2"
URL="https://github.com/pyodide/pyodide/releases/download/${VERSION}/pyodide-${VERSION}.tar.bz2"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="${ROOT}/data/pyodide-dist"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo "→ downloading pyodide ${VERSION} (~200 MB)…"
curl -fL --progress-bar -o "${TMP}/pyodide.tar.bz2" "${URL}"

echo "→ extracting into ${DEST}…"
mkdir -p "${DEST}"
tar -xjf "${TMP}/pyodide.tar.bz2" -C "${TMP}"
cp -R "${TMP}/pyodide/." "${DEST}/"

count=$(find "${DEST}" -maxdepth 1 -type f | wc -l | tr -d ' ')
size=$(du -sh "${DEST}" | cut -f1)
echo "✓ done — ${count} files (${size}) in ${DEST}"
