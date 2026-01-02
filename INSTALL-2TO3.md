# 2to3 Installation Instructions for WSL

The `2to3` tool is needed to convert Python 2 code to Python 3. Please install it by running these commands in WSL:

```bash
# Open WSL
wsl

# Install the package (you'll need to enter your password)
sudo apt-get update
sudo apt-get install -y python3-lib2to3

# Verify installation
python3 -m lib2to3 --help
```

## Alternative: Use pip to install 2to3

If the above doesn't work, try:

```bash
pip install 2to3
```

## After Installation

Once installed, let me know and I'll continue with the automated Python 2 to Python 3 conversion.
