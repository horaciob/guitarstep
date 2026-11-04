#!/usr/bin/env python
"""Compatibility shim: `python listener.py ...` is the same as `guitarr ...`."""
from guitarr.cli import main

if __name__ == "__main__":
    main()
