#!/usr/bin/env python3
"""Entry point for the paper-orchestra CLI."""
import sys

if sys.version_info < (3, 10):  # keep this file readable by old Pythons, so they can say so
    sys.stderr.write("Python 3.10 or newer is required; this is python3 %d.%d.%d\n" % tuple(sys.version_info[:3]))
    sys.exit(2)

from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from po.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
