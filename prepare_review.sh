#!/usr/bin/env bash
#
# prepare_review.sh
#
# Pre-flight for an AI4R review run. Called by the /ai4r workflow
# at Step 0. Validates inputs, creates the standard directory layout, and
# extracts any zipped reproduction packages.
#
# Usage:
#   ./assets/prepare_review.sh <review_title>
#
# Exit codes:
#   0  success
#   2  bad usage (missing or malformed review_title)
#   3  required input missing (paper.pdf not found)
#   4  extraction failed

set -euo pipefail

# ---------------------------------------------------------------------------
# Argument handling
# ---------------------------------------------------------------------------
if [[ $# -ne 1 ]]; then
    echo "usage: $0 <review_title>" >&2
    exit 2
fi

REVIEW_TITLE="$1"

# Kebab-case validation: lowercase alphanumerics plus hyphens, must not
# start with a hyphen. Same regex the workflow uses.
if ! [[ "$REVIEW_TITLE" =~ ^[a-z0-9][a-z0-9-]*$ ]]; then
    echo "error: review_title must be kebab-case (got: '$REVIEW_TITLE')" >&2
    exit 2
fi

REVIEW_DIR="$(pwd)/ai4r/${REVIEW_TITLE}"
LOG="${REVIEW_DIR}/logs/workflow.log"

# ---------------------------------------------------------------------------
# Directory layout
# ---------------------------------------------------------------------------
# Create each folder explicitly. The note in ai4r.md flags that combining
# them into one mkdir occasionally misbehaves on some shells.
mkdir -p "${REVIEW_DIR}/input/assets"
mkdir -p "${REVIEW_DIR}/kbe"
mkdir -p "${REVIEW_DIR}/cqv"
mkdir -p "${REVIEW_DIR}/er"
mkdir -p "${REVIEW_DIR}/review"
mkdir -p "${REVIEW_DIR}/logs"

# Initialize log
{
    echo "==== AI4R run: ${REVIEW_TITLE} ===="
    echo "started_at: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "host: $(hostname)"
    echo "cwd: $(pwd)"
    echo "git_sha: $(git -C "$(pwd)" rev-parse --short HEAD 2>/dev/null || echo 'not-a-git-repo')"
} > "${LOG}"

# ---------------------------------------------------------------------------
# Validate paper.pdf is present
# ---------------------------------------------------------------------------
PAPER="${REVIEW_DIR}/input/paper.pdf"
if [[ ! -f "${PAPER}" ]]; then
    {
        echo "ERROR: paper.pdf not found at ${PAPER}"
        echo "Place the manuscript at that path before running this script."
    } | tee -a "${LOG}" >&2
    exit 3
fi
echo "paper_pdf: OK ($(wc -c < "${PAPER}") bytes)" | tee -a "${LOG}"

# ---------------------------------------------------------------------------
# Extract any .zip archives in input/assets/
# ---------------------------------------------------------------------------
shopt -s nullglob
zip_files=( "${REVIEW_DIR}/input/assets"/*.zip )
shopt -u nullglob

if [[ ${#zip_files[@]} -eq 0 ]]; then
    echo "assets_zips: none found (skipping extraction)" | tee -a "${LOG}"
else
    for zip_file in "${zip_files[@]}"; do
        echo "extracting: ${zip_file}" | tee -a "${LOG}"
        # Use the project's tool so behavior matches what agents will see.
        if ! python3 -c "
from tools.tools import run_tool
import sys, json
result = run_tool('extract_zip', zip_filepath='${zip_file}')
print(json.dumps(result))
if not result.get('success', False):
    sys.exit(1)
" >> "${LOG}" 2>&1; then
            echo "ERROR: extraction failed for ${zip_file}" | tee -a "${LOG}" >&2
            exit 4
        fi
    done
fi

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------
{
    echo "preflight: OK"
    echo "review_dir: ${REVIEW_DIR}"
} | tee -a "${LOG}"
