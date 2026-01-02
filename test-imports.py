#!/usr/bin/env python3
"""Test imports after Python 3 conversion"""

import sys
sys.path.insert(0, 'src')

print("Testing Python 3 imports...")
print()

try:
    from Pellmonsrv import pellmonsrv
    print("✓ pellmonsrv imports successfully")
except Exception as e:
    print(f"✗ pellmonsrv import failed: {e}")

try:
    from Pellmonweb import pellmonweb
    print("✓ pellmonweb imports successfully")
except Exception as e:
    print(f"✗ pellmonweb import failed: {e}")

try:
    from Pellmonsrv import database
    print("✓ database imports successfully")
except Exception as e:
    print(f"✗ database import failed: {e}")

print()
print("Import test complete!")
