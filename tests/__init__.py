"""Test package: makes the root modules, evaluation scripts and tools importable."""
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
for _folder in (_ROOT, _ROOT / "evaluation", _ROOT / "tools", _ROOT / "tests"):
    if str(_folder) not in sys.path:
        sys.path.insert(0, str(_folder))
