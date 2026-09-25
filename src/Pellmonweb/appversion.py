#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Application version shown in the web UI.

The VERSION file at the repository root is the single source of truth. CI bumps
it on every feat:/fix: merge to master and the Docker image copies it to
/app/VERSION, so the page always shows the release the image was built from.
"""
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
_VERSION_FILE = os.path.normpath(os.path.join(_HERE, '..', '..', 'VERSION'))


def get_version(path=_VERSION_FILE):
    """Return the version string, or 'dev' when no VERSION file is readable."""
    try:
        with open(path, 'r') as f:
            version = f.read().strip()
    except (IOError, OSError):
        return 'dev'
    return version or 'dev'
