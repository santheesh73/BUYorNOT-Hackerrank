"""Pytest fixtures and configuration for BUYorNOT test suite."""

import sys
from pathlib import Path

# Ensure code directory and repo root are in sys.path
repo_root = Path(__file__).resolve().parent.parent
code_dir = repo_root / "code"

for p in [code_dir, repo_root]:
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))
