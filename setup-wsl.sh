#!/bin/bash
# WSL 2 Development Environment Setup for PellMon Python 3 Migration
# Run this script in WSL to set up the complete development environment

set -e  # Exit on error

echo "=========================================="
echo "PellMon WSL 2 Development Environment Setup"
echo "=========================================="
echo ""

# Update package lists
echo "Step 1: Updating package lists..."
sudo apt-get update

# Install system dependencies
echo ""
echo "Step 2: Installing system dependencies..."
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
    libdbus-glib-1-dev \
    libgirepository1.0-dev \
    build-essential \
    git \
    autoconf \
    automake

echo ""
echo "Step 3: Verifying Python version..."
python3 --version

# Navigate to PellMon directory (assumes it's accessible via /mnt/d/)
PELLMON_DIR="/mnt/d/Antigravity/PellMon-master"

if [ ! -d "$PELLMON_DIR" ]; then
    echo ""
    echo "ERROR: PellMon directory not found at $PELLMON_DIR"
    echo "Please adjust the PELLMON_DIR variable in this script."
    exit 1
fi

cd "$PELLMON_DIR"
echo ""
echo "Working directory: $(pwd)"

# Create Python 3 virtual environment
echo ""
echo "Step 4: Creating Python 3 virtual environment..."
if [ -d "venv-wsl" ]; then
    echo "Virtual environment already exists. Removing old one..."
    rm -rf venv-wsl
fi
python3 -m venv venv-wsl

# Activate virtual environment
echo ""
echo "Step 5: Activating virtual environment..."
source venv-wsl/bin/activate

# Upgrade pip
echo ""
echo "Step 6: Upgrading pip..."
pip install --upgrade pip

# Create requirements file for WSL (includes all dependencies)
echo ""
echo "Step 7: Creating WSL-specific requirements file..."
cat > requirements-wsl.txt << 'EOF'
# WSL/Linux-specific requirements with all dependencies
# Cross-platform dependencies
pyserial>=3.5
CherryPy>=18.8.0
Mako>=1.2.0
python-dateutil>=2.8.2
argcomplete>=2.0.0

# Optional dependencies
ws4py>=0.5.1

# Plugin dependencies
pyownet>=0.10.0
pycryptodome>=3.15.0
xtea>=0.7.1
pyowm>=3.3.0

# Note: rrdtool, dbus-python, and PyGObject are installed via system packages
# They should be available through the system Python packages
EOF

# Install Python dependencies
echo ""
echo "Step 8: Installing Python dependencies..."
pip install -r requirements-wsl.txt

# Verify installations
echo ""
echo "=========================================="
echo "Installation Complete!"
echo "=========================================="
echo ""
echo "Installed packages:"
pip list
echo ""
echo "Python version:"
python --version
echo ""
echo "System packages (should include rrdtool, dbus, gi):"
python3 -c "import rrdtool; print('✓ rrdtool:', rrdtool.__version__)" 2>/dev/null || echo "✗ rrdtool not available"
python3 -c "import dbus; print('✓ dbus-python available')" 2>/dev/null || echo "✗ dbus-python not available"
python3 -c "import gi; print('✓ PyGObject available')" 2>/dev/null || echo "✗ PyGObject not available"

echo ""
echo "=========================================="
echo "Next Steps:"
echo "=========================================="
echo "1. Activate the virtual environment:"
echo "   source venv-wsl/bin/activate"
echo ""
echo "2. Run 2to3 to convert Python 2 to Python 3:"
echo "   python -m lib2to3 -n src/"
echo ""
echo "3. Test the installation:"
echo "   cd src"
echo "   python Pellmonsrv/pellmonsrv.py --help"
echo ""
echo "Environment ready for Python 3 migration!"
