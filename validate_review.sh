#!/usr/bin/env bash
#
# validate_review.sh
#
# Post-flight for an AI4R review run. Called by the /ai4r kilocode workflow
# at Step 5. Verifies all required output files exist, parses the JSON
# files, and checks that mandatory top-level keys are present.
#
# Usage:
#   ./assets/validate_review.sh <review_title>
#
# Exit codes:
#   0  all required outputs present and well-formed
#   2  bad usage
#   5  one or more required outputs missing
#   6  a JSON output failed to parse or is missing required keys

set -euo pipefail

if [[ $# -ne 1 ]]; then
    echo "usage: $0 <review_title>" >&2
    exit 2
fi

REVIEW_TITLE="$1"
REVIEW_DIR="$(pwd)/ai4r/${REVIEW_TITLE}"
LOG="${REVIEW_DIR}/logs/workflow.log"

if [[ ! -d "${REVIEW_DIR}" ]]; then
    echo "error: review directory not found: ${REVIEW_DIR}" >&2
    exit 2
fi

# ---------------------------------------------------------------------------
# Required outputs and their type
# ---------------------------------------------------------------------------
# Format: "<relative_path>|<file_type>"
#   file_type is one of: json, md
REQUIRED=(
    "kbe/kbe_output.json|json"
    "kbe/notes.md|md"
    "cqv/cqv_output.json|json"
    "cqv/repo_analysis.md|md"
    "er/er_output.json|json"
    "review/final_review.md|md"
    "review/exhaustive_audit_report.md|md"
    "review/checklist.md|md"
    "review/risk_matrix.json|json"
)

# Mandatory top-level keys per JSON output. Edit when the schema evolves.
# Format: "<relative_path>|<space-separated keys>"
# Indexed array (not associative) for bash 3.2 compatibility: macOS still
# ships bash 3.2 and `declare -A` was added in bash 4.0.
REQUIRED_KEYS=(
    "kbe/kbe_output.json|paper_id status"
    "cqv/cqv_output.json|paper_id status"
    "er/er_output.json|status"
    "review/risk_matrix.json|paper_id paper_title assessed_at assessment_status risk_score risk_level verdict issues required_changes upstream_status"
)

# ---------------------------------------------------------------------------
# Existence + size check
# ---------------------------------------------------------------------------
missing=()
empty=()

echo "---- validation: ${REVIEW_TITLE} ----" | tee -a "${LOG}"

for entry in "${REQUIRED[@]}"; do
    rel="${entry%|*}"
    typ="${entry#*|}"
    path="${REVIEW_DIR}/${rel}"

    if [[ ! -f "${path}" ]]; then
        missing+=("${rel}")
        printf "MISSING  %s\n" "${rel}" | tee -a "${LOG}"
        continue
    fi

    size=$(wc -c < "${path}")
    if [[ ${size} -lt 2 ]]; then
        empty+=("${rel}")
        printf "EMPTY    %-50s (%d bytes)\n" "${rel}" "${size}" | tee -a "${LOG}"
        continue
    fi

    printf "OK       %-50s (%d bytes, %s)\n" "${rel}" "${size}" "${typ}" | tee -a "${LOG}"
done

if [[ ${#missing[@]} -gt 0 || ${#empty[@]} -gt 0 ]]; then
    {
        echo "validation FAILED: ${#missing[@]} missing, ${#empty[@]} empty"
        echo "missing: ${missing[*]:-none}"
        echo "empty: ${empty[*]:-none}"
    } | tee -a "${LOG}" >&2
    exit 5
fi

# ---------------------------------------------------------------------------
# JSON schema sanity check
# ---------------------------------------------------------------------------
schema_errors=()

for entry in "${REQUIRED_KEYS[@]}"; do
    rel="${entry%|*}"
    keys="${entry#*|}"
    path="${REVIEW_DIR}/${rel}"

    if ! python3 - "${path}" "${keys}" >> "${LOG}" 2>&1 <<'PY'
import json, sys
path, keys_str = sys.argv[1], sys.argv[2]
try:
    with open(path) as f:
        obj = json.load(f)
except json.JSONDecodeError as e:
    print(f"PARSE_ERROR {path}: {e}", file=sys.stderr)
    sys.exit(1)
if not isinstance(obj, dict):
    print(f"NOT_AN_OBJECT {path}: top-level is {type(obj).__name__}", file=sys.stderr)
    sys.exit(1)
missing = [k for k in keys_str.split() if k not in obj]
if missing:
    print(f"MISSING_KEYS {path}: {missing}", file=sys.stderr)
    sys.exit(1)
print(f"SCHEMA_OK {path}")
PY
    then
        schema_errors+=("${rel}")
        echo "SCHEMA_FAIL ${rel}" | tee -a "${LOG}" >&2
    fi
done

if [[ ${#schema_errors[@]} -gt 0 ]]; then
    echo "validation FAILED on schema: ${schema_errors[*]}" | tee -a "${LOG}" >&2
    exit 6
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
verdict=$(python3 -c "
import json
with open('${REVIEW_DIR}/review/risk_matrix.json') as f:
    print(json.load(f).get('verdict', 'UNKNOWN'))
")
risk_score=$(python3 -c "
import json
with open('${REVIEW_DIR}/review/risk_matrix.json') as f:
    print(json.load(f).get('risk_score', 'NA'))
")
# Patch 0069: surface assessment_status so the gate output distinguishes
# clean Review runs from upstream-degraded or reconciliation-failed runs.
# `validation: PASS` still means only "files exist and schemas conform"
# (its narrow but real meaning); the assessment_status line is the
# multi-dimensional health signal, companion to validate_review.sh's
# file-conformance check.
assessment_status=$(python3 -c "
import json
with open('${REVIEW_DIR}/review/risk_matrix.json') as f:
    print(json.load(f).get('assessment_status', 'unknown'))
")

{
    echo "validation: PASS"
    echo "assessment_status: ${assessment_status}"
    echo "verdict: ${verdict}"
    echo "risk_score: ${risk_score}"
    echo "review_dir: ${REVIEW_DIR}"
    echo "ended_at: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
} | tee -a "${LOG}"
