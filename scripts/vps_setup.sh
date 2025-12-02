#!/bin/bash
# MAMMON VPS Setup Script for Ubuntu 22.04
# This script prepares a fresh Ubuntu 22.04 VPS for running MAMMON

set -e  # Exit on error

echo "=== MAMMON VPS Setup ==="
echo "This script will install all dependencies for MAMMON on Ubuntu 22.04"
echo ""

# Update system
echo "[1/6] Updating system packages..."
sudo apt update && sudo apt upgrade -y

# Install Python 3.11
echo "[2/6] Installing Python 3.11..."
sudo apt install -y software-properties-common
sudo add-apt-repository -y ppa:deadsnakes/ppa
sudo apt update
sudo apt install -y python3.11 python3.11-venv python3.11-dev python3-pip git curl

# Set Python 3.11 as default (optional)
sudo update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1

# Install Poetry
echo "[3/6] Installing Poetry..."
curl -sSL https://install.python-poetry.org | python3 -

# Add Poetry to PATH
export PATH="$HOME/.local/bin:$PATH"
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc

# Verify installations
echo "[4/6] Verifying installations..."
python3 --version
poetry --version

# Navigate to project directory (assumes repo is already cloned/synced)
echo "[5/6] Setting up MAMMON project..."
cd ~/mammon || cd /root/mammon || { echo "Error: mammon directory not found"; exit 1; }

# Install project dependencies
echo "Installing Python dependencies via Poetry..."
poetry install --no-dev

# Create data directory
mkdir -p data

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Next steps:"
echo "1. Copy your .env file to $(pwd)/.env"
echo "   Example: scp /path/to/local/.env user@vps:~/mammon/.env"
echo ""
echo "2. Install the systemd service:"
echo "   sudo cp scripts/mammon.service /etc/systemd/system/"
echo "   sudo systemctl daemon-reload"
echo "   sudo systemctl enable mammon"
echo ""
echo "3. Start MAMMON:"
echo "   sudo systemctl start mammon"
echo ""
echo "4. Monitor logs:"
echo "   journalctl -u mammon -f"
echo ""
echo "5. Check status:"
echo "   sudo systemctl status mammon"
echo ""
