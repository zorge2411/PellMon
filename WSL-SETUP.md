# WSL 2 Development Environment for PellMon

## Overview

This guide helps you set up a complete WSL 2 (Windows Subsystem for Linux) development environment for the PellMon Python 3 migration. WSL provides access to Linux-specific dependencies that aren't available on Windows.

## Prerequisites

- Windows 10 version 2004+ or Windows 11
- WSL 2 installed and configured
- A Linux distribution installed (Ubuntu, Debian, etc.)

## Current WSL Status

**Detected WSL Installation:**

- Default Distribution: Debian
- WSL Version: 2
- Status: Running

**Available Distributions:**

- Debian (Running, WSL 2)
- docker-desktop (Running, WSL 2)

## Quick Start

### Option 1: Automated Setup (Recommended)

Run the provided setup script in WSL:

```bash
# From Windows PowerShell, access WSL
wsl

# Navigate to PellMon directory
cd /mnt/d/Antigravity/PellMon-master

# Make script executable
chmod +x setup-wsl.sh

# Run setup script
./setup-wsl.sh
```

The script will:

1. Update package lists
2. Install system dependencies (Python 3, rrdtool, dbus, etc.)
3. Create Python 3 virtual environment (`venv-wsl`)
4. Install all Python dependencies
5. Verify installations

### Option 2: Manual Setup

If you prefer manual setup or need to customize:

#### 1. Access WSL and Navigate to Project

```bash
# From PowerShell
wsl

# Navigate to PellMon (Windows D: drive is mounted at /mnt/d/)
cd /mnt/d/Antigravity/PellMon-master
```

#### 2. Install System Dependencies

```bash
sudo apt-get update
sudo apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    python3-dev \
    python3-rrdtool \
    python3-dbus \
    python3-gi \
    rrdtool \
    dbus \
    libdbus-1-dev \
    build-essential \
    git \
    autoconf \
    automake
```

#### 3. Create Virtual Environment

```bash
python3 -m venv venv-wsl
source venv-wsl/bin/activate
pip install --upgrade pip
```

#### 4. Install Python Dependencies

```bash
pip install -r requirements-wsl.txt
```

## Verifying Installation

After setup, verify all dependencies are available:

```bash
# Activate virtual environment
source venv-wsl/bin/activate

# Check Python version
python --version

# Verify system packages
python -c "import rrdtool; print('rrdtool:', rrdtool.__version__)"
python -c "import dbus; print('dbus-python: OK')"
python -c "import gi; print('PyGObject: OK')"

# Verify pip packages
pip list
```

## Working in WSL

### Accessing Windows Files

Windows drives are mounted under `/mnt/`:

- `C:\` → `/mnt/c/`
- `D:\` → `/mnt/d/`

Your PellMon directory:

- Windows: `d:\Antigravity\PellMon-master`
- WSL: `/mnt/d/Antigravity/PellMon-master`

### Git Configuration

Git is shared between Windows and WSL, but you may need to configure line endings:

```bash
# In WSL, configure git to handle line endings
git config --global core.autocrlf input
```

### Running Commands

Always activate the virtual environment first:

```bash
cd /mnt/d/Antigravity/PellMon-master
source venv-wsl/bin/activate

# Now you can run Python commands
python src/Pellmonsrv/pellmonsrv.py --help
```

## Advantages of WSL for PellMon Development

✅ **Full Linux Compatibility**

- Access to `rrdtool`, `dbus-python`, `PyGObject`
- Native DBUS support
- Serial port access (with configuration)

✅ **Seamless Integration**

- Access Windows files directly
- Use Windows editors (VS Code with WSL extension)
- Share git repository between Windows and WSL

✅ **Testing Environment**

- Test on actual target platform (Linux)
- Verify DBUS integration
- Test hardware interfaces

## Common Issues

### Issue: Permission Denied on Script

```bash
chmod +x setup-wsl.sh
```

### Issue: Can't Find PellMon Directory

Adjust the path in the script or navigate manually:

```bash
cd /mnt/d/Antigravity/PellMon-master
```

### Issue: System Packages Not Found

Some Python system packages need to be imported from system Python:

```bash
# Use system Python for testing
/usr/bin/python3 -c "import rrdtool"
```

## Next Steps After Setup

1. **Run 2to3 Analysis** (Phase 2)

   ```bash
   source venv-wsl/bin/activate
   python -m lib2to3 -n src/
   ```

2. **Apply 2to3 Transformations**

   ```bash
   python -m lib2to3 -w -n src/
   ```

3. **Test Imports**

   ```bash
   cd src
   python -c "from Pellmonsrv import pellmonsrv"
   ```

## VS Code Integration (Optional)

For the best development experience:

1. Install "WSL" extension in VS Code
2. Open PellMon in WSL:

   ```bash
   code /mnt/d/Antigravity/PellMon-master
   ```

3. VS Code will run in WSL mode with full Linux support

## Environment Comparison

| Feature | Windows (venv-py3) | WSL (venv-wsl) |
|---------|-------------------|----------------|
| Python 3 | ✓ | ✓ |
| pyserial | ✓ | ✓ |
| CherryPy | ✓ | ✓ |
| rrdtool | ✗ | ✓ |
| dbus-python | ✗ | ✓ |
| PyGObject | ✗ | ✓ |
| **Recommended for** | Code editing | Testing & Migration |

## Summary

WSL 2 provides the complete Linux environment needed for PellMon development, including all system dependencies. Use WSL for the Python 3 migration and testing, while keeping the flexibility to edit files in Windows.
