#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
    Copyright (C) 2013  Anders Nylund

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 2 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>.

PellMon semver bump decision (D-03/D-05/D-06).

Computes the next semantic version from Conventional Commit messages since the
last v* tag (or full history if no tag exists yet), using the exact three-rule
priority order (ported 1:1 from the reference increment-version.ps1 algorithm):

    1. ANY line containing the substring 'BREAKING CHANGE' (case-sensitive,
       not anchored) -> major
    2. else ANY line starting with 'feat:' or 'feat(scope):'               -> minor
    3. else ANY line starting with 'fix:' or 'fix(scope):'                 -> patch
    4. else no-op (None) -- nothing is written, nothing is built

    pellmon_version_bump.py decide [--dry-run] [--type major|minor|patch]
                                    [--version-file VERSION]

Prints "bump=<major|minor|patch|none>" and (when a bump happened) "version=<x.y.z>"
to stdout, GITHUB_OUTPUT-format. When the GITHUB_OUTPUT environment variable is
set (running under GitHub Actions), the same lines are also appended to that file.

Per D-08, this script never reads or writes any Autotools version file --
VERSION is the sole source of truth for the Docker image tag only.
"""

import argparse
import logging
import os
import re
import subprocess
import sys

logger = logging.getLogger('version_bump')

_FEAT_RE = re.compile(r'^feat(\(.+\))?:')
_FIX_RE = re.compile(r'^fix(\(.+\))?:')


def decide_bump(commit_messages):
    """Return 'major' | 'minor' | 'patch' | None from a list of commit message lines.

    Priority is existence-based, not chronological: if the range contains both a
    fix: commit and a BREAKING CHANGE mention (anywhere, in any order), the
    result is 'major'. Performs zero I/O -- pure function (D-06).
    """
    if any('BREAKING CHANGE' in line for line in commit_messages):
        return 'major'
    if any(_FEAT_RE.match(line) for line in commit_messages):
        return 'minor'
    if any(_FIX_RE.match(line) for line in commit_messages):
        return 'patch'
    return None


def apply_bump(version_tuple, bump_type):
    """Return the next (major, minor, patch) tuple for the given bump_type."""
    major, minor, patch = version_tuple
    if bump_type == 'major':
        return (major + 1, 0, 0)
    if bump_type == 'minor':
        return (major, minor + 1, 0)
    if bump_type == 'patch':
        return (major, minor, patch + 1)
    raise ValueError('unknown bump_type: %r' % bump_type)


def parse_version(text):
    """Parse 'MAJOR.MINOR.PATCH' into a 3-tuple of ints. Hard-fails on anything else --
    no v-prefix stripping, no coercion (Pitfall 3)."""
    stripped = text.strip()
    parts = stripped.split('.')
    if len(parts) != 3:
        raise ValueError('malformed version %r: expected exactly 3 dot-separated parts' % text)
    try:
        return tuple(int(p) for p in parts)
    except ValueError:
        raise ValueError('malformed version %r: all 3 parts must be integers' % text)


def format_version(version_tuple):
    """Join a (major, minor, patch) tuple into 'MAJOR.MINOR.PATCH'."""
    return '.'.join(str(p) for p in version_tuple)


def read_version(path):
    """Read and parse the VERSION file at path."""
    with open(path, 'r') as f:
        return parse_version(f.read())


def write_version(path, version_tuple):
    """Write version_tuple to path as 'MAJOR.MINOR.PATCH\\n' (no v-prefix)."""
    with open(path, 'w') as f:
        f.write(format_version(version_tuple) + '\n')


def _run(argv, check=True, capture=False):
    """Single choke point for external commands: list argv, never a shell."""
    logger.debug('run: %r', argv)
    kw = {}
    if capture:
        kw['stdout'] = subprocess.PIPE
        kw['stderr'] = subprocess.PIPE
        kw['text'] = True
    return subprocess.run(argv, check=check, **kw)


def last_tag():
    """Return the most recent v* tag, or None if the repo has no tags yet (Pitfall 4)."""
    result = _run(['git', 'describe', '--tags', '--abbrev=0'], check=False, capture=True)
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def commits_since(tag):
    """Return the commit message lines (already .splitlines()-ed) since tag, or full
    history when tag is None."""
    if tag:
        argv = ['git', 'log', '%s..HEAD' % tag, '--pretty=%B']
    else:
        argv = ['git', 'log', '--pretty=%B']
    result = _run(argv, capture=True)
    return result.stdout.splitlines()


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description='Compute (and optionally apply) the next semver bump for PellMon')
    sub = parser.add_subparsers(dest='command', required=True)

    decide = sub.add_parser('decide', help='Compute and apply the next version bump')
    decide.add_argument('--dry-run', action='store_true',
                         help='Print the computed bump/version without writing VERSION')
    decide.add_argument('--type', choices=['major', 'minor', 'patch'], default=None,
                         help='Force a specific bump, skipping commit analysis')
    decide.add_argument('--version-file', default='VERSION',
                         help='Path to the VERSION file (default: VERSION)')
    return parser.parse_args(argv)


def _emit(bump, version):
    """Print GITHUB_OUTPUT-format lines to stdout, and append to $GITHUB_OUTPUT when set."""
    lines = ['bump=%s' % bump]
    if version is not None:
        lines.append('version=%s' % version)
    for line in lines:
        print(line)
    github_output = os.environ.get('GITHUB_OUTPUT')
    if github_output:
        with open(github_output, 'a') as f:
            for line in lines:
                f.write(line + '\n')


def _decide(args):
    if args.type:
        bump = args.type
    else:
        bump = decide_bump(commits_since(last_tag()))

    if bump is None:
        logger.info('no release needed')
        _emit('none', None)
        return 0

    current = read_version(args.version_file)
    new_version = apply_bump(current, bump)
    if not args.dry_run:
        write_version(args.version_file, new_version)
    _emit(bump, format_version(new_version))
    return 0


def main(argv=None):
    args = parse_args(argv)
    logging.basicConfig(level=logging.INFO, stream=sys.stderr, format='%(message)s')
    try:
        if args.command == 'decide':
            return _decide(args)
        return 0
    except (ValueError, OSError, subprocess.CalledProcessError) as e:
        sys.stderr.write('error: %s\n' % e)
        return 1


if __name__ == '__main__':
    sys.exit(main())
