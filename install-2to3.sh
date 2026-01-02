#!/bin/bash
# Install 2to3 tool for Python 2 to Python 3 conversion
# Run this script in WSL with: sudo ./install-2to3.sh

echo "Installing 2to3 conversion tool..."
apt-get update
apt-get install -y python3-lib2to3 2to3

echo ""
echo "Verifying installation..."
which 2to3
2to3 --version

echo ""
echo "2to3 installation complete!"
