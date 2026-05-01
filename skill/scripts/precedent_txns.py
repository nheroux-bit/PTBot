#!/usr/bin/env python3
"""PTBot CLI wrapper for the installed skill."""

from _bootstrap import ensure_ptbot_importable

ensure_ptbot_importable()

from ptbot.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
