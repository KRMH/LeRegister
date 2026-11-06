import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def lint(cwd: Path, extra_env_path: Path | None = None):
    env = None
    if extra_env_path:
        import os

        env = {**os.environ, "PYTHONPATH": str(extra_env_path)}
    return subprocess.run(
        [str(Path(sys.executable).parent / "lint-imports"), "--config", str(cwd / "pyproject.toml")],
        cwd=cwd, capture_output=True, text=True, env=env,
    )


def test_contract_passes():
    r = lint(ROOT, ROOT / "src")
    assert r.returncode == 0, r.stdout + r.stderr


def test_contract_fails_on_forbidden_import(tmp_path):
    shutil.copytree(ROOT / "src", tmp_path / "src")
    shutil.copy(ROOT / "pyproject.toml", tmp_path / "pyproject.toml")
    for bad in ["import sqlite3", "import httpx", "from telegram import Update",
                "from leregister.adapters.telegram import bot"]:
        target = tmp_path / "src" / "leregister" / "core" / "bad.py"
        target.write_text(bad + "\n")
        r = lint(tmp_path, tmp_path / "src")
        assert r.returncode != 0, f"contract should fail for: {bad}\n{r.stdout}"
        target.unlink()
