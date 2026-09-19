#!/usr/bin/env python3
"""Compare two pytest JUnit-XML files by per-test outcome only.

Phase 2 (exception-visibility-retrofit) converts print()/bare-except calls
to logger.exception()/logger.debug() calls inside existing except blocks.
That conversion legitimately changes captured log text (a traceback is now
written where a one-line message used to be), so a raw text diff of pytest
console output would falsely register as a regression.

This script instead diffs structured per-test outcomes (pass/fail/error/
skip) extracted from JUnit XML <testcase> elements, deliberately ignoring
any captured stdout/stderr log-text child elements and <properties>
content. See .planning/phases/02-exception-visibility-retrofit/02-RESEARCH.md
section "Exact before/after comparison mechanism" (and Pitfall 5) for the
full rationale.

Usage:
    python junit-outcome-diff.py <before.xml> <after.xml>

Exit code 0: no test present in BEFORE changed outcome or disappeared in
             AFTER (test IDs that appear only in AFTER are reported but do
             not affect the exit code -- Phase 2 adds new test files whose
             IDs are legitimately absent from BEFORE).
Exit code 1: at least one BEFORE test_id changed outcome, or disappeared
             from AFTER entirely.
"""

import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def outcomes(path):
    """Parse a JUnit XML file into {test_id: outcome} pairs.

    test_id is f"{classname}::{name}" per <testcase>. outcome is one of
    'fail' (has a <failure> child), 'error' (has an <error> child), 'skip'
    (has a <skipped> child), or 'pass' (none of the above). Only these
    three structural child tags are inspected; captured stdout/stderr
    log-text child elements and <properties> are never read.
    """
    tree = ET.parse(path)
    result = {}
    for tc in tree.iter("testcase"):
        test_id = "%s::%s" % (tc.get("classname"), tc.get("name"))
        if tc.find("failure") is not None:
            result[test_id] = "fail"
        elif tc.find("error") is not None:
            result[test_id] = "error"
        elif tc.find("skipped") is not None:
            result[test_id] = "skip"
        else:
            result[test_id] = "pass"
    return result


def main(argv):
    if len(argv) != 3:
        print("Usage: python junit-outcome-diff.py <before.xml> <after.xml>")
        return 2

    before_path, after_path = argv[1], argv[2]
    for p in (before_path, after_path):
        if not Path(p).is_file():
            print("ERROR: file not found: %s" % p)
            return 2

    before = outcomes(before_path)
    after = outcomes(after_path)

    before_ids = set(before)
    after_ids = set(after)

    changed = {
        test_id: (before[test_id], after[test_id])
        for test_id in before_ids & after_ids
        if before[test_id] != after[test_id]
    }
    disappeared = sorted(before_ids - after_ids)
    added = sorted(after_ids - before_ids)

    print("BEFORE test count: %d" % len(before_ids))
    print("AFTER test count:  %d" % len(after_ids))
    print("CHANGED:     %d" % len(changed))
    print("DISAPPEARED: %d" % len(disappeared))
    print("ADDED:       %d (informational only, not a failure)" % len(added))

    if added:
        print()
        print("ADDED (present only in AFTER, informational):")
        for test_id in added:
            print("  %s -> %s" % (test_id, after[test_id]))

    if not changed and not disappeared:
        print()
        print("IDENTICAL pass/fail/skip status before and after")
        return 0

    print()
    if changed:
        print("CHANGED outcomes (before -> after):")
        for test_id in sorted(changed):
            b, a = changed[test_id]
            print("  %s: %s -> %s" % (test_id, b, a))
    if disappeared:
        print("DISAPPEARED (present in BEFORE, missing from AFTER):")
        for test_id in disappeared:
            print("  %s: %s -> MISSING" % (test_id, before[test_id]))

    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
