"""Stage application sources without local environments or test modules."""

from pathlib import Path
import shutil

root = Path(__file__).resolve().parents[1]
target = root / ".worker-build"
if target.exists():
    shutil.rmtree(target)
target.mkdir()
shutil.copy2(root / "worker.py", target / "worker.py")
shutil.copytree(root / "app", target / "app", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
