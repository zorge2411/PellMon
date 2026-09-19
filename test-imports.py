#!/usr/bin/env python3
"""Test imports after Python 3 conversion"""

import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
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

try:
    from Pellmonweb import pellmonconf
    print("✓ pellmonconf imports successfully")
except Exception as e:
    print(f"✗ pellmonconf import failed: {e}")

print()
print("Import test complete!")
