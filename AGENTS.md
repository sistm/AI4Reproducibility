# AGENTS.md

This file provides guidance to agents when working with code in this repository.

## Project Overview
- **Purpose**: AI framework for automated reproducibility evaluation of scientific papers
- **Stack**: Python 3.12+, Docker 29.2.1+, pymupdf

## Architecture
- Pipeline: KBE → CQV → ER (optional) → Review
- Entry point: tools/tools.py (central tool registry)
- Workflow definitions: .kilocode/workflows/ai4r.md

## Non-Obvious Patterns

### Tool Return Format
All tools in `tools/` return `{"success": bool, "error": str|None, ...}`. Always check `success` before using results.

### Docker Experiment Environment
- Only supported: Python 3.11, R 4.4 (see `SUPPORTED_ENGINES` in launch-env.py)
- Requires `experiment-run/` directory in project root
- Python deps via requirements.txt, R via renv.lock

### Bugs in launch-env.py (will cause runtime errors)
- Line 39: uses undefined `supported` (should be `SUPPORTED_ENGINES`)
- Line 83: syntax error `"-dit",,` - double comma

### Agent Definitions
- Use YAML frontmatter format (name, description fields)
- Review agent: agents/review/SKILL.md
- Output template: agents/review/assets/review-template.md

### Empty Placeholder Files (0 bytes)
- tools/cqv_agent/get-dependencies.py
- tools/er_agent/evaluate-results.py

### Output Directory Structure
- Reviews must output to: `/ai4r/{kebab-case-title}/`
- Title derived from paper title, lowercase, kebab-case
