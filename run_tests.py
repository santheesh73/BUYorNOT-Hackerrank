"""Convenience test runner that safely disables blocked global plugins."""

import os
import sys
from pathlib import Path

# Disable global plugins blocked by Windows Application Control policies
os.environ["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"

# Ensure repo and code paths are present
repo_root = Path(__file__).resolve().parent
code_dir = repo_root / "code"
for p in [code_dir, repo_root]:
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import pytest

if __name__ == "__main__":
    args = sys.argv[1:] if len(sys.argv) > 1 else ["-v"]
    sys.exit(pytest.main(args))
