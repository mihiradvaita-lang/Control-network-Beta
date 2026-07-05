#!/usr/bin/env python3
"""Cross-platform launcher (Windows / macOS / Linux).

Usage:  python run.py
Creates a local virtualenv, installs deps, then starts the server on
http://localhost:8000  (override with CN_PORT).
"""
from __future__ import annotations
import os, subprocess, sys, venv
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
IS_WIN = os.name == "nt"
PY = VENV / ("Scripts/python.exe" if IS_WIN else "bin/python")


def sh(*args):
    print("[CN]", " ".join(str(a) for a in args))
    subprocess.check_call(list(args))


def main():
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"  # ZDR: no .pyc on disk
    if not PY.exists():
        print("[CN] creating virtual environment...")
        venv.create(VENV, with_pip=True)
    sh(str(PY), "-m", "pip", "install", "-q", "--upgrade", "pip")
    sh(str(PY), "-m", "pip", "install", "-q", "-r", str(ROOT / "requirements.txt"))
    env_file = ROOT / ".env"
    if not env_file.exists():
        env_file.write_text((ROOT / ".env.example").read_text(encoding="utf-8"), encoding="utf-8")
        print("[CN] created .env (add your Claude key for AI narratives; optional)")
    port = os.environ.get("CN_PORT", "8000")
    print(f"\n[CN] Starting Control Network — open http://localhost:{port}  (Ctrl+C to stop)\n")
    os.chdir(ROOT)
    subprocess.call([str(PY), "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", port])


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as e:
        print("\n[CN] setup failed:", e)
        print("[CN] Make sure Python 3.10+ is installed and on PATH (python.org).")
        sys.exit(1)
