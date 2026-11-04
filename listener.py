#!/usr/bin/env python
"""Compatibilidad: `python listener.py ...` equivale a `guitarr ...`."""
from guitarr.cli import main

if __name__ == "__main__":
    main()
