#!/usr/bin/env python3
"""
Manual Python 2 to Python 3 conversion script for PellMon
Applies the most critical transformations identified in the analysis
"""

import os
import re
import sys
from pathlib import Path

def convert_print_statements(content):
    """Convert print statements to print() functions"""
    # Simple print statements without parentheses
    content = re.sub(r'\bprint\s+(["\'])', r'print(\1', content)
    content = re.sub(r'\bprint\s+([a-zA-Z_])', r'print(\1', content)
    return content

def convert_except_syntax(content):
    """Convert except Exception, e: to except Exception as e:"""
    content = re.sub(r'except\s+(\w+(?:\.\w+)*)\s*,\s*(\w+)\s*:', r'except \1 as \2:', content)
    return content

def convert_imports(content):
    """Convert Python 2 imports to Python 3"""
    replacements = {
        'import ConfigParser': 'import configparser',
        'from ConfigParser import': 'from configparser import',
        'import Queue': 'import queue',
        'import urllib2': 'import urllib.request',
        'import simplejson as json': 'import json',
    }
    
    for old, new in replacements.items():
        content = content.replace(old, new)
    
    return content

def convert_dict_methods(content):
    """Convert dict.iteritems() to dict.items()"""
    content = content.replace('.iteritems()', '.items()')
    content = content.replace('.iterkeys()', '.keys()')
    content = content.replace('.itervalues()', '.values()')
    return content

def convert_xrange(content):
    """Convert xrange() to range()"""
    content = re.sub(r'\bxrange\b', 'range', content)
    return content

def convert_file(filepath):
    """Convert a single Python file"""
    print(f"Converting: {filepath}")
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        original_content = content
        
        # Apply conversions
        content = convert_except_syntax(content)
        content = convert_imports(content)
        content = convert_dict_methods(content)
        content = convert_xrange(content)
        # Note: print statements need manual review
        
        if content != original_content:
            # Create backup
            backup_path = str(filepath) + '.py2bak'
            with open(backup_path, 'w', encoding='utf-8') as f:
                f.write(original_content)
            
            # Write converted content
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            
            print(f"  ✓ Converted (backup: {backup_path})")
            return True
        else:
            print(f"  - No changes needed")
            return False
            
    except Exception as e:
        print(f"  ✗ Error: {e}")
        return False

def main():
    src_dir = Path('src')
    
    if not src_dir.exists():
        print("Error: src/ directory not found")
        sys.exit(1)
    
    print("=" * 60)
    print("PellMon Python 2 to Python 3 Conversion")
    print("=" * 60)
    print()
    
    # Find all Python files
    py_files = list(src_dir.rglob('*.py'))
    print(f"Found {len(py_files)} Python files")
    print()
    
    converted_count = 0
    for py_file in py_files:
        if convert_file(py_file):
            converted_count += 1
    
    print()
    print("=" * 60)
    print(f"Conversion complete: {converted_count}/{len(py_files)} files modified")
    print("=" * 60)
    print()
    print("Next steps:")
    print("1. Review the changes with: git diff")
    print("2. Test imports: python -c 'from Pellmonsrv import pellmonsrv'")
    print("3. Fix any remaining issues manually")
    print("4. Commit changes: git commit -am 'Phase 2: Automated Python 3 conversion'")

if __name__ == '__main__':
    main()
