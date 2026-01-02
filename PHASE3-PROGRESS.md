# Phase 3 Progress: Manual Python 3 Fixes

**Status:** IN PROGRESS

## Completed Fixes

### 1. Import Fixes ✅

- **Queue module**: `import Queue` → `import queue`
- **ConfigParser**: Fixed incorrect `from configparser import configparser` → `from configparser import ConfigParser` (4 files)
- **GObject/GLib**: Updated DBUS bindings
  - `import glib` → `from gi.repository import GLib`
  - `import gobject` → `from gi.repository import GObject`
  - `gobject.threads_init()` → `GObject.threads_init()`
  - `gobject.MainLoop()` → `GLib.MainLoop()`

### 2. Relative Imports ✅

- **Pellmonsrv/**init**.py**: `from daemon import Daemon` → `from .daemon import Daemon`
- **Pellmonweb/**init**.py**: Fixed all relative imports to use explicit syntax (`.auth`, `.logview`, `.consumption`)

### 3. Print Statements ✅ (Partial)

Fixed in:

- `pellmonweb.py`: 3 print statements
- `daemon.py`: 1 print statement

### 4. File Operations ✅

- **daemon.py**: Replaced `file()` with `open()` (5 instances)
- Fixed buffering parameter: `open(file, 'a+', buffering=0)`

## Files Modified

- `src/Pellmonsrv/pellmonsrv.py`
- `src/Pellmonsrv/__init__.py`
- `src/Pellmonsrv/daemon.py`
- `src/Pellmonsrv/plugin_categories.py`
- `src/Pellmonsrv/plugins/raspberrygpio/__init__.py`
- `src/Pellmonsrv/plugins/owfs/__init__.py`
- `src/Pellmonsrv/plugins/consumption/__init__.py`
- `src/Pellmonweb/__init__.py`
- `src/Pellmonweb/pellmonweb.py`

## Remaining Issues

### 1. database.py

- Print statements need fixing
- Octal literal with leading zero (Python 3 requires `0o` prefix)

### 2. Missing Dependencies

- `cherrypy` not installed (web framework)
- May need additional packages

### 3. Additional Print Statements

- Still ~40+ print statements in other files to review

## Next Steps

1. Fix database.py issues
2. Install missing dependencies (cherrypy)
3. Continue fixing remaining print statements
4. Test basic functionality

---

**Git Commit:** Phase 3 manual fixes in progress
