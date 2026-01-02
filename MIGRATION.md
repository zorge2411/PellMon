# PellMon Python 2 to Python 3 Migration

## Current Environment Documentation

**Date:** 2026-01-02

### Python 2.7 Environment (Original)

**Python Version:** 2.7.x (original target)

**Core Dependencies:**

- rrdtool
- python-serial
- python-cherrypy3
- python-dbus
- python-mako
- python-gobject
- python-simplejson
- python-dateutil
- python-argcomplete

**Optional Dependencies:**

- python-ws4py (WebSocket support)

**Plugin-Specific Dependencies:**

- pyownet (OWFS plugin)
- python-crypto (NBEcom plugin - deprecated)
- xtea (NBEcom plugin)
- pyowm (Openweathermap plugin)

### Python 3 Environment (Target)

**Python Version:** 3.14.0 (current system)
**Target Compatibility:** Python 3.8+

**Core Dependencies (Python 3):**

- rrdtool>=1.7.0
- pyserial>=3.5
- CherryPy>=18.8.0
- dbus-python>=1.2.18
- Mako>=1.2.0
- PyGObject>=3.42.0
- python-dateutil>=2.8.2
- argcomplete>=2.0.0

**Optional Dependencies:**

- ws4py>=0.5.1

**Plugin Dependencies:**

- pyownet>=0.10.0 (OWFS)
- pycryptodome>=3.15.0 (NBEcom - replaces python-crypto)
- xtea>=0.7.1 (NBEcom)
- pyowm>=3.3.0 (Openweathermap)

### Migration Status

**Phase 1: Pre-Migration Preparation** ✓ COMPLETE

- [x] Git repository initialized
- [x] Baseline commit created (commit: 2ff7ab4)
- [x] Python 3 migration branch created
- [x] requirements.txt created
- [x] .gitignore updated for Python 3
- [x] Virtual environment created (venv-py3)

**Next Steps:**

- Install dependencies in virtual environment
- Run 2to3 analysis
- Begin automated code conversion

### Notes

- Original codebase: 303 files, 3.77 MB
- Git repository location: d:\Antigravity\PellMon-master
- Branch: python3-migration
- Virtual environment: venv-py3/
