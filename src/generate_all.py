#!/usr/bin/env python3
"""Run all generation steps: OPML + README from config/feeds.json."""

import subprocess
import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent


def main():
    subprocess.run([sys.executable, str(SRC_DIR / "generate_opml.py")], check=True)
    subprocess.run([sys.executable, str(SRC_DIR / "generate_readme.py")], check=True)
    print("OPML and README regenerated from config/feeds.json")


if __name__ == "__main__":
    main()
