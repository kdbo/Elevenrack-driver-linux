#!/usr/bin/env python3
"""Compatibility entry point for Debian/Ubuntu latency backend packaging."""
from pathlib import Path
import subprocess
import sys

if __name__ == '__main__':
    subprocess.run([sys.executable, str(Path(__file__).with_name('build-latency-package.py')),
                    '--format', 'deb', *sys.argv[1:]], check=True)
