#!/usr/bin/env python3
"""Redirect to the Cold Bot entry point. Run from repo root: python main.py --help"""
import subprocess
import sys
import os

root = os.path.dirname(os.path.abspath(__file__))
cold_bot_dir = os.path.join(root, "cold_bot")
main_py = os.path.join(cold_bot_dir, "main.py")
sys.exit(
    subprocess.run(
        [sys.executable, main_py] + sys.argv[1:],
        cwd=cold_bot_dir,
    ).returncode
)
